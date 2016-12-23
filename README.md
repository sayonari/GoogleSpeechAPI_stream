# google_speech_api_vad_stream

[Google Cloud Speech gRPC API を使ってストリーム音声認識をしたい！（簡易VAD付けた）](http://qiita.com/sayonari/items/a70118a468483967ad34)

- Simple [Voice Activity Detection](https://en.wikipedia.org/wiki/Voice_activity_detection)
- Client detects volume above threshold
- Connect to google after VAD
- Buffer to audio on connecting google and sends audio buffer when connected to google
- Repeating connect to google after VAD

## Install(mac)

- `brew install portaudio`

## Setup

- `pip install -r requirements.txt`

## Run

- `python transcribe_stream.py`

