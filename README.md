# GoogleSpeechAPI_stream

[Google Cloud Speech gRPC API を使ってストリーム音声認識をしたい！（簡易VAD付けた）](http://qiita.com/sayonari/items/a70118a468483967ad34)

- 簡易的な音声開始検出を実装し，音声が開始するまではPC側で監視
- 音声開始を検出してから，googleに接続開始
- 接続中の音声もバッファしておき，googleに繋がったらバッファから順に送信

## Install(mac)

- `brew install portaudio`

## Setup

- `pip install -r requirements.txt`

## Run

- `python transcribe_stream.py`

