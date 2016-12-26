#!/usr/bin/python
# -*- coding: utf-8 -*-
# ベースのソースは以下のものです
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/master/speech/grpc/transcribe_streaming.py

try:
    import pyaudio
except:
    print("PyAudio ImportError")
    print("")
    print("brew install portaudio or sudo apt-get install python-pyaudio python3-pyaudio")
    exit(1)
import time
import wave
import audioop
import math
import sys
import tempfile
import signal

import re

from gcloud.credentials import get_credentials
from google.cloud.grpc.speech.v1beta1 import cloud_speech_pb2 as cloud_speech
from google.rpc import code_pb2
from grpc.beta import implementations
from grpc.framework.interfaces.face.face import RemoteError, AbortionError

# 各種設定　#########################
flag_recog_repeat = True  # 音声認識を繰り返し行う場合　Trueにする
EXIT_WORD = u"(音声認識を終了します|ちちんぷいぷい|さようなら)"  # 音声認識を終了させる合言葉
LANG_CODE = 'ja-JP'  # a BCP-47 language tag

RATE = 16000  # サンプリングレート
CHANNELS = 1  # 録音チャンネル数

RECORD_SEC = 5  # 録音時間(sec)
DEV_INDEX = 0  # デバイスを指定

FRAME_SEC = 0.1  # 1フレームの時間（秒）　（0.1sec = 100ms）
CHUNK = int(RATE * FRAME_SEC)  # 1フレーム内のサンプルデータ数

SLEEP_SEC = FRAME_SEC / 4  # メインループ内でのスリープタイム（秒）
BUF_SIZE = CHUNK * 2  # 音声のバッファ・サイズ（byte）

DECIBEL_THRESHOLD = 50  # 録音開始のための閾値（dB)
START_FRAME_LEN = 4  # 録音開始のために，何フレーム連続で閾値を超えたらいいか
START_BUF_LEN = 5  # 録音データに加える，閾値を超える前のフレーム数　（START_FRAME_LENの設定によって，促音の前の音が録音されない問題への対処用）

# Google のサンプルプログラムより (Keep the request alive for this many seconds)
DEADLINE_SECS = 8 * 60 * 60
SPEECH_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

# バッファ用変数 #####################
frames = []
frames_startbuf = []



# コールバック関数 ###################
def callback(in_data, frame_count, time_info, status):
    global frames
    if frames == None:
        frames = []
    frames.append(in_data)
    return (None, pyaudio.paContinue)


# Creates an SSL channel ###########
def make_channel(host, port):
    ssl_channel = implementations.ssl_channel_credentials(None, None, None)
    creds = get_credentials().create_scoped([SPEECH_SCOPE])
    auth_header = (
        'Authorization',
        'Bearer ' + creds.get_access_token().access_token)
    auth_plugin = implementations.metadata_call_credentials(
        lambda _, cb: cb([auth_header], None),
        name='google_creds')

    composite_channel = implementations.composite_channel_credentials(
        ssl_channel, auth_plugin)

    return implementations.secure_channel(host, port, composite_channel)


# listen print loop ##################
def listen_print_loop(recognize_stream):
    recog_result = ''
    def raise_if_no_result(signum):
        if not recog_result:
            raise Exception()
    signal.signal(signal.SIGALRM, raise_if_no_result)
    signal.alarm(RECORD_SEC)
    try:
        for resp in recognize_stream:
            if resp.error.code != code_pb2.OK:
                return recog_result
            if resp.endpointer_type == "END_OF_AUDIO":
                return recog_result

            # 音声認識結果＆途中結果の表示 (受け取るデータの詳細は以下を参照のこと)
            # https://cloud.google.com/speech/reference/rpc/google.cloud.speech.v1beta1#google.cloud.speech.v1beta1.SpeechRecognitionAlternative
            for result in resp.results:
                if result.is_final:
                    print "is_final: " + str(result.is_final)

                for alt in result.alternatives:
                    print "conf:" + str(alt.confidence) + " stab:" + str(result.stability)
                    print "trans:" + alt.transcript
                    recog_result = alt.transcript

                # 音声認識終了（is_final: True）
                if result.is_final:
                    return recog_result
    except Exception:
        return recog_result

# request stream ####################
def request_stream(channels=CHANNELS, rate=RATE, chunk=CHUNK, language=LANG_CODE):
    recognition_config = cloud_speech.RecognitionConfig(
        encoding='LINEAR16',  # raw 16-bit signed LE samples
        sample_rate=rate,  # the rate in hertz
        language_code=language,  # a BCP-47 language tag
    )
    streaming_config = cloud_speech.StreamingRecognitionConfig(
        config=recognition_config,
        interim_results=True, single_utterance=True
    )

    yield cloud_speech.StreamingRecognizeRequest(
        streaming_config=streaming_config)

    while True:
        time.sleep(SLEEP_SEC)

        # バッファにデータが溜まったら，データ送信
        if len(frames) > 0:
            data_1frame = frames.pop(0)
            data_l2s = b''.join(map(str, data_1frame))
            wf.writeframes(data_l2s)  # waveファイルに書き込み
            yield cloud_speech.StreamingRecognizeRequest(audio_content=data_l2s)  # google ASR


# main ##############################
if __name__ == '__main__':
    print 'Start Rec!({})'.format(LANG_CODE)

    # pyaudioオブジェクトを作成 --------------------
    p = pyaudio.PyAudio()

    # ストリームを開始 (録音は別スレッドで行われる) ----
    stream = p.open(format=p.get_format_from_width(2),
                    channels=CHANNELS,
                    rate=RATE,
                    input_device_index=DEV_INDEX,
                    input=True,
                    output=False,
                    frames_per_buffer=CHUNK,
                    stream_callback=callback)

    stream.start_stream()

    # 録音用waveファイルのFileStream作成 ------------
    wf = wave.open(tempfile.TemporaryFile(), 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)

    while True:
        # フラグ初期化 ##################################
        flag_record_start = False  # 音量が規定フレーム分，閾値を超え続けたらTRUE

        # 録音開始までの処理 ##############################
        while not flag_record_start:
            try:
                time.sleep(SLEEP_SEC)
            except:
                continue

            # 促音用バッファが長過ぎたら捨てる（STARTフレームより更に前のデータを保存しているバッファ）
            if len(frames_startbuf) > START_BUF_LEN:
                del frames_startbuf[0:len(frames_startbuf) - START_BUF_LEN]

            # バッファにデータが溜まったら，録音開始するべきか判定 ---------
            if len(frames) > START_FRAME_LEN:
                # 1フレーム内の音量計算--------------------------------
                for i in range(START_FRAME_LEN):
                    data = frames[i]
                    rms = audioop.rms(data, 2)
                    decibel = 20 * math.log10(rms) if rms > 0 else 0
                    sys.stdout.write("\rrms %3d decibel %f" %(rms,decibel))
                    sys.stdout.flush()

                    # 音量が閾値より小さかったら，データを捨てループを抜ける ----
                    if decibel < DECIBEL_THRESHOLD:
                        frames_startbuf.append(frames[0:i + 1])
                        del frames[0:i + 1]
                        break

                    # 全フレームの音量が閾値を超えていたら，録音開始！！ ----
                    # 更に，framesの先頭に，先頭バッファをプラス
                    # これをしないと「かっぱ」の「かっ」など，促音の前の音が消えてしまう
                    if i == START_FRAME_LEN - 1:
                        flag_record_start = True
                        frames = frames_startbuf + frames

        # googleサーバに接続 ############################
        print "\nconnecting ...."
        with cloud_speech.beta_create_Speech_stub(
                make_channel('speech.googleapis.com', 443)) as service:
            try:
                print "success to connect."
            except:
                print "connection error."

        # 録音開始後の処理 ###############################
        req_stream = request_stream()
        recog_result = listen_print_loop(
            service.StreamingRecognize(
                req_stream, DEADLINE_SECS))

        # 音声認識 繰り返しの終了判定 #####################
        if re.match(EXIT_WORD, recog_result):
            print('Exiting..')
            exit(0)

        # 音声認識繰り返ししない設定 ######################
        if not flag_recog_repeat:
            break

    # ストリームを止めて，クローズ
    print 'Closing audio stream....'
    stream.stop_stream()
    stream.close()

    p.terminate()  # pyaudioオブジェクトを終了
    wf.close()  # wavefile stream クローズ

    print 'End Rec!'

