# AI YouTube Video Generator

![GitHub stars](https://img.shields.io/github/stars/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub forks](https://img.shields.io/github/forks/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub last commit](https://img.shields.io/github/last-commit/tuvshinorg/AI-YouTube-Video-Generator)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flutter](https://img.shields.io/badge/Flutter-Windows%20desktop-02569B.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

![Codex](https://img.shields.io/badge/OpenAI-Codex%20CLI-black.svg)
![llama.cpp](https://img.shields.io/badge/llama.cpp-local%20LLM-orange.svg)
![HuggingFace Flux](https://img.shields.io/badge/HuggingFace-Flux-yellow.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Video%20Processing-red.svg)
![YouTube API](https://img.shields.io/badge/YouTube-API%20v3-red.svg)
![Whisper](https://img.shields.io/badge/OpenAI-Whisper-black.svg)

## Чадварлаг AI/ML хөгжүүлэгч хайж байна уу?

**Холбоо барих: [tuvshin.org@gmail.com](mailto:tuvshin.org@gmail.com)**

[![Portfolio](https://img.shields.io/badge/💼-Available%20for%20Hire-brightgreen.svg?style=for-the-badge)](mailto:tuvshin.org@gmail.com)

---

## Татаж авах

**[⬇ Windows-ийн хамгийн сүүлийн хувилбарыг татах](https://github.com/tuvshinorg/AI-YouTube-Video-Generator/releases/latest)** — release хуудсан дээр хоёр сонголт бий:

* **`AI-YouTube-Video-Generator-Setup-vX.Y.Z.exe`** (санал болгох хувилбар) — энгийн Windows installer. Ажиллуулаад зааврын дагуу суулгахад Start Menu/Desktop shortcut автоматаар үүснэ. App нь database болон render хийсэн видеонуудаа өөрийнхөө хажууд хадгалдаг тул user түвшинд суух бөгөөд admin/UAC permission шаардахгүй.
* **`AI-YouTube-Video-Generator-Windows-vX.Y.Z.zip`** — яг ижил app-ийн portable хувилбар; хүссэн газраа задлаад `ytgen_manager.exe`-г шууд ажиллуулна, installer шаардлагагүй.

Аль хувилбарыг сонгосон ч энэ build нь **бүрэн бие даасан** — `pipeline.exe` нь бүх pipeline-ийг (CPU-only torch, transformers, Whisper, fastText) өөртөө багтаасан тул Codex-only замыг ашиглах үед тусдаа Python суулгах шаардлагагүй ([AI Providers](#ai-providers)-г харна уу). Танд хэрэгтэй ганц зүйл нь Codex login бөгөөд доорх [First Run](#first-run) хэсэг app дотроос хэрхэн нэвтрэхийг алхам алхмаар заана.

Өөрөө build хийх бол: `flutter build windows` + `pyinstaller backend.spec` + `pyinstaller pipeline.spec` нь шаардлагатай хэсгүүдийг үүсгэнэ ([Flutter Manager App](#flutter-manager-app)-г харна уу); `iscc installer.iss` ([Inno Setup](https://jrsoftware.org/isinfo.php) шаардлагатай) нь бэлдсэн release folder-оос installer үүсгэнэ.

---

## Юу хийдэг вэ?

Нийтлэл, санаа эсвэл сэдвийг шууд нийтлэхэд бэлэн босоо видео болгон хувиргана — narration, AI-аар үүсгэсэн зураг, subtitle, хөгжим, transition бүгдийг нэг товчоор native Windows app дээр хийх эсвэл cron/Task Scheduler ашиглан бүрэн автоматаар ажиллуулах боломжтой.

```
Your text / idea
      ↓
  LLM  (llama.cpp locally, or Codex CLI)      → 6 scenes: narration + image prompt
      ↓
  Images  (HuggingFace Flux, OpenAI Images, or Codex's image_gen)
      ↓
  Edge TTS  (auto-picks a Mongolian voice if the scene is written in Mongolian)
      ↓
  FFmpeg  → clips + subtitles (Whisper, or a Mongolian-finetuned Whisper) + transitions + music mix
      ↓
  YouTube API → published  (or saved as .mp4 for manual upload)
```

Дээрх үе шат бүрт provider-ийг сольж ашиглах боломжтой — бүрэн local (`llama.cpp` + Flux, GPU шаардлагатай), бүрэн ChatGPT/Codex login-аар (GPU болон local model шаардлагагүй), эсвэл хооронд нь хослуулж болно. Доорх [AI Providers](#ai-providers) хэсгийг харна уу.

---

## Ашиглах боломжууд

* **Нүүр царайгүй YouTube Shorts / TikTok суваг** — news article paste хийх эсвэл санаагаа бичихэд narration, subtitle, background music бүхий босоо видео хэдхэн минутын дотор үүсэж, автоматаар upload хийх эсвэл эхлээд шалгахын тулд файл болгон хадгална.
* **Контентыг дахин ашиглах** — blog post, press release эсвэл урт script-ийг video editor нээхгүйгээр short-form видео болгоно.
* **Хоёр хэлтэй (English/Mongolian) контент** — аль ч хэлээр бичиж болно, тэр ч байтугай нэг project дотор хоёр хэлийг хольж болно. Scene бүрийн narration, subtitle болон transcription автоматаар тохирох хэлээ сонгоно — [Mongolian Language Support](#mongolian-language-support)-г харна уу.
* **GPU-гүй / хүчин чадал багатай компьютер** — `AI_PROVIDER=codex`, `IMAGE_PROVIDER=codex` тохируулснаар бүх text болон image pipeline таны Codex/ChatGPT login-аар ажиллана. Зөвхөн subtitle (Whisper) болон video compositing (FFmpeg) local ажиллах бөгөөд хоёулаа CPU дээр боломжийн ажиллана.
* **Хүний оролцоогүй batch production** — хэд хэдэн санааг queue-д нэмээд cron (Linux/WSL) эсвэл Windows Task Scheduler-аар pipeline-ийг хуваарийн дагуу ажиллуулж, дараа нь app-ийн "Finished" жагсаалтаас үр дүнгээ шалгана.
* **Portfolio / automation жишээ** — LLM, image generation, TTS, ASR болон video composition-ийг нэг state-machine pipeline болгон холбож, дээр нь бодит desktop UI хийсэн бүрэн ажиллагаатай жишээ.

---

## Анх ажиллуулах

Backend одоо аюулгүйгээр автоматаар тохируулж болох бүх зүйлээ өөрөө тохируулж, өөрөө хийж чадахгүй хэсгийг тодорхой зааж өгдөг:

* **Directory, `.env`, database бүгд backend анх эхлэх үед автоматаар үүснэ** — app ашиглаж эхлэхийн өмнө `setup.sh` эсвэл `create.py` гараар ажиллуулах шаардлагагүй.
* **Language-ID болон Mongolian-Whisper model-ууд автоматаар татагдана** (~1 MB болон ~3.2 GB). Тухайн model анх удаа шаардлагатай scene дээр ашиглагдах үед татагдах бөгөөд Activity log дээр татаж байгааг харуулна. Олон минут юу ч болоогүй мэт гацахгүй.
* **Python dependency бол бүрэн далд байдлаар автоматжуулах боломжгүй цорын ганц хэсэг** — app таны аль Python environment-д dependency суулгахыг хүсэж байгааг мэдэх боломжгүй бөгөөд progress харуулахгүйгээр олон минут үргэлжлэх install-ийг аюулгүй ажиллуулах боломжгүй. Хэрэв dependency байхгүй бол dashboard дээр ажиллуулах яг command, хаанаас ажиллуулах болон "Recheck" товчтой banner гарна:

```bash
⚠ Python dependencies aren't installed yet
pip install -r requirements.txt          [copy]
Run it from: C:\...\AI-YouTube-Video-Generator
```

* **Codex login** (`AI_PROVIDER=codex` эсвэл `IMAGE_PROVIDER=codex` үед л харагдана): banner нь Node.js + Codex CLI-г автоматаар суулгах сонголт өгнө. Таны өөрөө terminal дээр бичих байсан command-уудыг app ажиллуулж, output-ийг live харуулна. Дараа нь device-login flow-оор нэвтрүүлнэ — link нээгээд clipboard дээр автоматаар хуулсан code-ийг paste хийхэд хангалттай. Terminal шаардлагагүй.

Хоёр banner алга болсны дараа "Make the video" шууд ажиллана.

---

## Түргэн эхлэх (source-оос)

```bash
git clone https://github.com/tuvshinorg/AI-YouTube-Video-Generator.git
cd AI-YouTube-Video-Generator
bash setup.sh
```

`setup.sh` нь Python эхлэхээс өмнө хийх шаардлагатай зүйлсийг гүйцэтгэнэ:

* Repo path-ийг илрүүлж `.env` файлд бичнэ
* Runtime directory-уудыг үүсгэнэ (`logs/`, `temp/*/`, `final/`, `song/*/`, `optic/`, `models/`)
* CUDA илрүүлээд боломжтой бол `llama-cpp-python`-ийг GPU support-тай суулгана
* Бүх pip dependency-г суулгана
* SQLite database initialize хийнэ
* Cron job суулгана (зөвхөн Linux/WSL — default нь цаг тутам)

Үүнээс хойших бүх зүйл (directory/DB repair, Codex install/login) app анх асах үед автоматаар хийгдэнэ — [First Run](#first-run)-г харна уу.

**Хамгийн хурдан зам (GPU болон local model шаардлагагүй):** `.env` файлд доорх хоёр мөрийг тохируулаад app эсвэл `make run-file`-ийг шууд ажиллуулна:

```bash
AI_PROVIDER=codex
IMAGE_PROVIDER=codex
```

**Local/offline зам:** GGUF model болон Flux repo-г тохируулна:

```bash
LLAMA_MODEL_PATH=./models/Llama-3.2-3B-Instruct-Q6_K.gguf
FLUX_MODEL_ID=enhanceaiteam/Flux-Uncensored-V2
```

```bash
huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \
    Llama-3.2-3B-Instruct-Q6_K.gguf --local-dir ./models
```

---

## Interactive CLI

```bash
make cli          # or: python cli.py
```

```
╔══════════════════════════════════════════╗
║  AI YouTube Video Generator — Manager   ║
╚══════════════════════════════════════════╝

  Pipeline: ○ idle   DB: /path/to/main.db

  1)  Add RSS feed
  2)  Check RSS feeds
  3)  Import from JSON
  4)  Enter text manually
  5)  Show queue
  6)  Run pipeline (api)       ← upload to YouTube
  7)  Run pipeline (file)      ← save .mp4 locally
  8)  Stop running pipeline
  q)  Quit
```

CLI subcommand-уудыг scripting-д мөн ашиглаж болно:

```bash
python cli.py add-rss                  # validate & import an RSS feed
python cli.py check-rss                # show all RSS groups + entry counts
python cli.py add-json entries.json    # bulk import from JSON file
python cli.py add-text                 # paste text, no RSS needed
python cli.py queue                    # live queue status table
python cli.py run --output api         # run now, upload to YouTube
python cli.py run --output file        # run now, save .mp4 for manual upload
python cli.py stop                     # SIGTERM the running pipeline
```

### Текст гараар оруулах

RSS feed байхгүй юу? Шууд бичнэ:

```
Enter text manually → type or paste → finish with a line containing ---
```

Pipeline үүнийг RSS article-тэй яг адилхан боловсруулж, бүрэн видео үүсгэнэ.

### JSON import формат

```json
{
  "group": "my-source",
  "entries": [
    { "title": "Optional title", "text": "Full article body here..." },
    { "title": "Another one",    "text": "More content..." }
  ]
}
```

---

## Flutter Manager App

Native Windows desktop app (`app/`) нь энэ төслийг ажиллуулах үндсэн интерфэйс юм — санаагаа paste хийх, render явцыг live харах, finished/queued/errored project-уудыг үзэх, устгах, Codex login удирдах бүгдийг нэг цонхоос хийнэ. Энэ нь `cli.py`-ийн адил үйлдлүүдийг wrap хийсэн жижиг FastAPI backend (`api.py`, `backend.exe` болгон package хийгдсэн)-тэй холбогдоно.

**App backend-ийн бүх lifecycle-ийг өөрөө удирдана** — `backend.exe`-г random port болон random auth token ашиглан өөрөө асааж, app хаагдах үед унтраана (эсвэл app force-kill хийгдвэл Windows унтраана). Гараар server асаах, ямар нэг command бичих шаардлагагүй — яг хэрхэн ажилладгийг болон acceptance checklist-ийг [`docs/CONNECTION.md`](docs/CONNECTION.md)-ээс харна уу.

**1. Backend-ийг нэг удаа build хийх (эсвэл `api.py` өөрчилсний дараа):**

```bash
make backend-exe    # pyinstaller -> dist/backend/, copied into app/windows/backend/
```

`backend.exe` зориудаар жижиг (~35 MB unpacked) хэвээр үлддэг — torch/transformers/whisper/llama-cpp-ийг өөрөө import хийдэггүй. Зөвхөн `pipeline.py` нь эдгээрийг import хийгээд ердийн Python subprocess хэлбэрээр ажиллана. Иймээс prebuilt exe ашигласан ч Python dependency суулгах алхмыг алгасах боломжгүй ([First Run](#first-run)-г харна уу).

**2. App-ийг ажиллуулах эсвэл build хийх:**

```bash
cd app
flutter run -d windows          # dev
flutter build windows           # → app/build/windows/x64/runner/Release/
```

Ингээд л боллоо — аль нэгийг нь ажиллуулахад backend автоматаар асна.

**Dev mode** (UI дээр hot-reload ашиглан manually эхлүүлсэн backend-тэй ажиллах, жишээ нь `uvicorn api:app --reload`): `YTGEN_BACKEND_URL` (мөн шаардлагатай бол `YTGEN_BACKEND_TOKEN`) тохируулаад `--dev` дамжуулна:

```bash
YTGEN_BACKEND_URL=http://127.0.0.1:8000 flutter run -d windows -- --dev
```

> Android support өмнө нь scaffold хийгдсэн бөгөөд ижил зарчмаар ажилладаг боловч platform folder-ийг одоогоор устгасан. Хүссэн үедээ `app/` folder дотроос `flutter create --platforms=android .` ажиллуулаад буцааж үүсгэж болно.

---

## AI Provider-ууд

AI ашигладаг үе шат бүр `.env`-ээр provider-оо тусдаа сонгодог — өөрийн hardware/account-аас хамааран хольж ашиглаж болно.

| Үе шат                            | Env var          | Сонголтууд                            | Тайлбар                                                                                                                                                                                                                                                                                            |
| --------------------------------- | ---------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Text (scenes, title, description) | `AI_PROVIDER`    | `llama` (default) · `codex`           | `llama` нь local GGUF-ийг llama.cpp ашиглан ажиллуулна — боломжийн хурдтай ажиллуулахын тулд GPU хэрэгтэй. `codex` нь Codex CLI-г ажиллуулна — GPU шаардлагагүй боловч Codex/ChatGPT login хэрэгтэй.                                                                                               |
| Images                            | `IMAGE_PROVIDER` | `flux` (default) · `openai` · `codex` | `flux` HuggingFace diffusers ашиглан local ажиллана — GPU шаардлагатай. `openai` Images API дуудна (төлбөртэй, `OPENAI_API_KEY` шаардлагатай). `codex` Codex-ийн built-in `image_gen` tool ашиглана — `AI_PROVIDER=codex`-тэй ижил login ашиглах бөгөөд тусдаа API key эсвэл billing шаардлагагүй. |
| Subtitles                         | *(automatic)*    | generic Whisper · Mongolian fine-tune | Үргэлж local ажиллана. Scene бүрийн language detection тохирох model-ийг автоматаар сонгоно — config шаардлагагүй.                                                                                                                                                                                 |
| Narration voice                   | *(automatic)*    | `TTS_VOICE` · `TTS_VOICE_MN`          | Scene бүрийн language detection тохирох voice-ийг мөн автоматаар сонгоно.                                                                                                                                                                                                                          |

**GPU огт хэрэггүй зам:** `AI_PROVIDER=codex` + `IMAGE_PROVIDER=codex` нь local model болон dedicated GPU огт шаарддаггүй — зөвхөн Whisper (CPU-friendly) болон FFmpeg local ажиллана. [First Run](#first-run) хэсгийн Codex banner яг үүнд зориулагдсан.

### Codex-ийг ийм байдлаар ашиглах тухай

* **Auth нь `codex login` ямар account-аар нэвтэрснээс хамаарна.** Хэрэв API key биш ChatGPT Plus/Pro login ашиглаж байгаа бол энэ login нь нэг төхөөрөмж дээр interactive terminal session-д зориулагдсан бөгөөд unattended backend automation-д зориулагдаагүй гэдгийг анхаарна уу — ийм байдлаар ашиглах нь OpenAI-ийн usage terms-тэй зөрчилдөж болзошгүй. Өөрийн account дээр хэрхэн ашиглахаа та өөрөө шийднэ; энэ project аль нэг хувилбарыг албаддаггүй.
* **Шинэ login эхлүүлэхэд хуучин login шууд дуусна**, шинэ login процесс бүрэн дуусаагүй байсан ч гэсэн — "cancel хийгээд хуучин session-аа хадгалах" боломжгүй.
* **Codex өөрийн usage limit-тэй.** Pipeline нь дараалсан image call-уудын хооронд (`CODEX_IMAGE_DELAY`, default 180s) pause хийж limit-ээс хэтрэхээс сэргийлдэг. Олон scene-тэй project бүрэн render болоход хугацаа орж болно; энэ delay нь зориудын бөгөөд app гацсан гэсэн үг биш (Activity log үүнийг тодорхой харуулна).

---

## Монгол хэлний дэмжлэг

Project-ийн бусад хэсэг ямар хэл дээр байхаас үл хамааран scene бүрийн text narration болон subtitle үүсгэхээс өмнө бодит language-identification model болох [fastText-ийн `lid.176`](https://fasttext.cc/docs/en/language-identification.html) (176 хэл, анхны хэрэглээнд ~1 MB автоматаар татагдана)-оор шалгагдана:

* **Монгол (`mn`) гэж танигдсан бол** → narration-д `TTS_VOICE_MN` (`mn-MN-YesuiNeural` default) ашиглана, subtitle transcription-д [`Tsedee/whisper-large-v3-turbo-mn-2`](https://huggingface.co/Tsedee/whisper-large-v3-turbo-mn-2) ашиглана. Энэ нь generic model-оос Монгол яриаг мэдэгдэхүйц илүү зөв таньдаг Whisper fine-tune юм. Монгол scene анх удаа transcription хийх үед ~3.2 GB model автоматаар татагдана.
* **Бусад бүх хэл** → ердийн `TTS_VOICE` болон generic multilingual Whisper model ашиглана. Үүнд Russian, Ukrainian, Kazakh болон бусад Cyrillic script ашигладаг хэлүүд багтана — тэдгээрийг Монгол гэж үзэж Mongolian-specific model руу явуулахгүй.

Энэ нь "Cyrillic character байгаа эсэх" гэсэн энгийн таамаг биш, бодит classification юм — Монгол хэлний хоёр нэмэлт Cyrillic үсэг (Өө, Үү) байсан ч зөвхөн script шалгавал бусад Cyrillic хэлнээс найдвартай ялгах боломжгүй.

---

## Output Mode-ууд

| Mode              | Command         | Үр дүн                                                                               |
| ----------------- | --------------- | ------------------------------------------------------------------------------------ |
| **api** (default) | `make run`      | Full pipeline → YouTube руу автоматаар upload                                        |
| **file**          | `make run-file` | Full pipeline → `.mp4` файл `final/` дотор хадгалагдаж, гараар upload хийх боломжтой |

Flutter app-ийн "Make the video" товч үргэлж `file` mode ашиглана — YouTube upload хийхэд OAuth credential хэрэгтэй бөгөөд app үүнийг өөрөө тохируулдаггүй ([YouTube API Setup](#youtube-api-setup)-г харна уу). Auto-upload хийх бол `make run` эсвэл CLI ашиглана.

---

## Make Target-ууд

```bash
make setup        first-time install + cron
make cli          interactive manager
make api          REST API for the Flutter manager app
make backend-exe  build backend.exe for the Flutter app to spawn
make run          full pipeline → YouTube upload
make run-file     full pipeline → save .mp4 locally

make feed         module 01 only: text/RSS → scenes
make image        module 02 only: images
make voice        module 03 only: TTS
make clip         module 04 only: clips
make subtitle     module 05 only: subtitles (Whisper)
make transition   module 06 only: transitions
make mix          module 07 only: music mix
make final        module 08 only: final render
make upload       module 09 only: YouTube upload
make clean        module 10 only: delete temp files

make cron-show    print current crontab
make cron-remove  remove the pipeline cron entry
```

---

## Тохиргоо (`.env`)

`.env.example`-ийг `.env` болгон хуулж тохируулна (хэрэв `.env` байхгүй бол app анх асахдаа үүнийг автоматаар хийдэг — [First Run](#first-run)-г харна уу):

```bash
cp .env.example .env
```

| Variable                     | Default                                    | Тайлбар                                                                                                           |
| ---------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `BASE_DIR`                   | auto-detected                              | Repo-ийн absolute path                                                                                            |
| `AI_PROVIDER`                | `llama`                                    | `llama` (local llama.cpp) эсвэл `codex` (Codex CLI, зөвхөн text)                                                  |
| `CODEX_TIMEOUT`              | `120`                                      | Нэг text `codex exec` call-ийн нийт дээд хугацаа (секунд)                                                         |
| `LLAMA_MODEL_PATH`           | `./models/Llama-3.2-3B-Instruct-Q6_K.gguf` | GGUF model-ийн path                                                                                               |
| `LLAMA_N_CTX`                | `4096`                                     | LLM context window (tokens)                                                                                       |
| `LLAMA_N_GPU`                | `-1`                                       | GPU layers: `-1` = бүгд GPU дээр, `0` = зөвхөн CPU                                                                |
| `LLAMA_VERBOSE`              | `false`                                    | llama.cpp token output харуулах                                                                                   |
| `IMAGE_PROVIDER`             | `flux`                                     | `flux` (local), `openai` (Images API), эсвэл `codex` (Codex-ийн image_gen tool)                                   |
| `CODEX_IMAGE_TIMEOUT`        | `240`                                      | Нэг image `codex exec` call-ийн нийт дээд хугацаа (секунд)                                                        |
| `CODEX_IMAGE_DELAY`          | `180`                                      | Codex usage limit-ээс хэтрэхгүй байхын тулд дараалсан image call-уудын хооронд хүлээх хугацаа                     |
| `CODEX_STARTUP_IDLE_TIMEOUT` | `180`                                      | `codex exec` тодорхой хугацаанд ямар ч activity үзүүлэхгүй бол эрт terminate хийх хугацаа                         |
| `FLUX_MODEL_ID`              | `enhanceaiteam/Flux-Uncensored-V2`         | Flux-compatible ямар ч HuggingFace repo                                                                           |
| `FLUX_CPU_OFFLOAD`           | `true`                                     | Call хооронд model-ийг CPU руу offload хийх (VRAM хэмнэнэ)                                                        |
| `FLUX_WIDTH` / `FLUX_HEIGHT` | `540` / `960`                              | Output image хэмжээ (Shorts-д зориулсан portrait)                                                                 |
| `FLUX_STEPS`                 | `20`                                       | Diffusion steps                                                                                                   |
| `FLUX_GUIDANCE`              | `3.5`                                      | Guidance scale                                                                                                    |
| `OPENAI_API_KEY`             | —                                          | Зөвхөн `IMAGE_PROVIDER=openai` үед ашиглана                                                                       |
| `OPENAI_IMAGE_MODEL`         | `gpt-image-1`                              | OpenAI Images API model                                                                                           |
| `OPENAI_IMAGE_SIZE`          | `1024x1536`                                | Portrait, Flux-ийн default aspect-тай таарна                                                                      |
| `TTS_VOICE`                  | `en-US-AvaNeural`                          | Edge TTS voice (`edge-tts --list-voices` ажиллуулж жагсаалтыг харна)                                              |
| `TTS_VOICE_MN`               | `mn-MN-YesuiNeural`                        | Монгол scene илрэхэд автоматаар сонгогдоно — [Mongolian Language Support](#mongolian-language-support)-г харна уу |
| `WHISPER_MODEL_MN`           | `Tsedee/whisper-large-v3-turbo-mn-2`       | Монгол scene-д ашиглагдах Whisper fine-tune                                                                       |
| `YT_CLIENT_SECRET`           | `client_secret.json`                       | YouTube OAuth client secret filename                                                                              |
| `YT_CREDENTIALS`             | `credentials.storage`                      | OAuth token storage filename                                                                                      |
| `API_PORT`                   | `8000`                                     | Зөвхөн `python api.py` / `make api` dev mode-д ашиглагдах port                                                    |
| `PYTHON_EXECUTABLE`          | —                                          | Зөвхөн frozen `backend.exe` дотор шаардлагатай — энэ project-ийн dependency суусан Python руу заана               |

---

## Системийн шаардлага

Desktop app нь Windows-only (Flutter Windows + backend process lifecycle-д Win32 API ашиглана). Харин `pipeline.py`/`cli.py` нь энгийн Python тул Flutter app ашиглахгүй бол Linux/macOS дээр мөн ажиллана.

Ямар provider сонгосноос requirement ихээхэн хамаарна ([AI Providers](#ai-providers)-г харна уу):

| Component  | Codex path (`AI_PROVIDER=codex` + `IMAGE_PROVIDER=codex`) | Local path (`llama` + `flux`)        |
| ---------- | --------------------------------------------------------- | ------------------------------------ |
| GPU / VRAM | Шаардлагагүй                                              | Хамгийн багадаа 8 GB, 16 GB+ зөвлөмж |
| RAM        | 8 GB                                                      | 16–32 GB                             |
| Storage    | ~5 GB (model хэрэгтэй үедээ автоматаар татагдана)         | 20–50 GB (GGUF + Flux weights)       |
| Account    | ChatGPT/Codex login                                       | Шаардлагагүй                         |
| ffmpeg     | Аль ч замд шаардлагатай                                   | Аль ч замд шаардлагатай              |

---

## Directory бүтэц

```text
AI-YouTube-Video-Generator/
├── pipeline.py          unified pipeline (all 10 modules)
├── cli.py               interactive CLI manager
├── api.py               REST API for the Flutter manager app (self-configures on startup)
├── backend.spec         PyInstaller spec -> backend.exe (make backend-exe)
├── app/                 Flutter manager app (Windows desktop)
│   └── lib/stage_ring.dart   the tinted progress-ring widget used across the UI
├── docs/CONNECTION.md   backend<->frontend connection design + checklist
├── create.py            database initialiser (auto-run by api.py if main.db is missing)
├── setup.sh             one-shot bootstrap script
├── Makefile             convenience targets
├── requirements.txt     pip dependencies
├── .env.example         config template
├── .env                 your config (git-ignored; auto-created from .env.example if missing)
├── main.db              SQLite database (git-ignored; auto-created if missing)
├── pipeline.lock        runtime lock file (git-ignored)
├── client_secret.json   YouTube OAuth secret (git-ignored)
├── credentials.storage  OAuth tokens (git-ignored)
├── logs/                pipeline logs + cron.log
├── models/              GGUF / auto-downloaded models (git-ignored)
│   └── lid.176.ftz      fastText language-ID model (auto-downloaded)
├── song/                background music library
│   ├── bright/          .mp3 files per mood
│   ├── calm/
│   ├── dark/
│   ├── dramatic/
│   ├── funky/
│   ├── happy/
│   ├── inspirational/
│   └── sad/
├── optic/               optical flare clips (1.mp4 – 9.mp4)
├── temp/                intermediate render files (auto-cleaned)
│   ├── audio/
│   ├── clip/
│   ├── codex/           scratch dir for AI_PROVIDER=codex (per-call schema/output files)
│   ├── image/
│   ├── mix/
│   ├── subtitle/
│   ├── temp/
│   ├── video/
│   └── voice/
└── final/               finished .mp4 files
```

---

## YouTube API тохиргоо

1. [Google Cloud Console](https://console.cloud.google.com/) руу орно
2. Project үүсгээд **YouTube Data API v3**-г enable хийнэ
3. OAuth 2.0 credentials үүсгэнэ (Desktop app)
4. `client_secret.json` татаж аваад repo root-д байрлуулна
5. Анхны upload ажиллах үед browser нээгдэж OAuth consent авна — token автоматаар хадгалагдана

---

## Cron (Автомат хуваарь)

`setup.sh` нь cron entry-г автоматаар суулгана (Linux/WSL). Default нь цаг тутам.

Schedule өөрчлөхийн тулд ажиллуулахаас өмнө `setup.sh` доторх `CRON_SCHEDULE` мөрийг өөрчилнө:

```bash
CRON_SCHEDULE="0 * * * *"    # every hour (default)
CRON_SCHEDULE="0 */6 * * *"  # every 6 hours
CRON_SCHEDULE="0 2 * * *"    # daily at 02:00
```

Pipeline нь lock file (`pipeline.lock`) ашигладаг тул зэрэгцээ хоёр run эхлэхээс аюулгүй хамгаална.

```bash
make cron-show      # see installed cron entry
make cron-remove    # remove it
```

Cron output `logs/cron.log` файлд бичигдэнэ. Native Windows дээр WSL ашиглахгүй бол Windows Task Scheduler-аар `python pipeline.py`-г schedule хийж болно, эсвэл Flutter app-ийн "Run now" товчоор гараар ажиллуулна.

---

## Pipeline Module-ууд

| #  | Module         | Юу хийдэг                                                                                                                                                 |
| -- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01 | **feed**       | Text/RSS queue → LLM (`llama.cpp` эсвэл Codex) ашиглан narration + image prompt + title + description + music genre бүхий 6 scene үүсгэнэ                 |
| 02 | **image**      | Scene бүрт Flux, OpenAI Images эсвэл Codex-ийн `image_gen` tool ашиглан нэг AI image үүсгэнэ                                                              |
| 03 | **voice**      | Narration → Edge TTS-аар speech үүсгэнэ, Монгол scene илрэхэд Монгол voice автоматаар сонгоно                                                             |
| 04 | **clip**       | Image + audio + optical flare-ийг нэгтгэн scene бүрийн video clip үүсгэнэ                                                                                 |
| 05 | **subtitle**   | Whisper (generic эсвэл автоматаар сонгогдох Mongolian fine-tune) ашиглан audio transcription хийж, word-level highlighted subtitle видеон дээр burn хийнэ |
| 06 | **transition** | Scene clip-үүдийг smooth transition ашиглан холбоно                                                                                                       |
| 07 | **mix**        | Background music (LLM сонгосон genre) давхарлаж, echo/EQ болон normalisation хийнэ                                                                        |
| 08 | **final**      | Video + mixed audio нэгтгээд `final/{seedId}.mp4` үүсгэнэ                                                                                                 |
| 09 | **upload**     | Title + description-тай YouTube руу upload хийнэ (`--output file` mode үед алгасана)                                                                      |
| 10 | **clean**      | Upload хийгдсэн video-ны temp file-уудыг устгана                                                                                                          |

Алдаа гарч болох үе шат бүр project дээр failure мэдээллийг (`seedErrorStep`/`seedErrorMsg`) хадгалдаг тул app-ийн "Needs attention" хэсэгт шууд харагдана — project ямар ч тайлбаргүйгээр "in progress" дээр үүрд гацахгүй.

---

## Алдаа засах

**Dashboard дээр "Python dependencies aren't installed yet" гарч байна**

Banner дээр харагдаж байгаа яг command-ийг (`pip install -r requirements.txt`) repo root-оос ажиллуулаад "Recheck" дарна. [First Run](#first-run)-г харна уу.

**Project "In progress" дээр алдаагүй гацсан**

Одоо ийм зүйл гарах ёсгүй — pipeline-ийн үе шат бүр failure мэдээллийг project дээр хадгалдаг тул "Needs attention" хэсэг рүү орно. Хэрэв ийм асуудал гарсаар байвал `logs/pipeline.log`-ийн холбогдох мөрүүдтэй issue нээнэ үү.

**Codex image/text call timeout болж байна**

`CODEX_STARTUP_IDLE_TIMEOUT` (default 180s) нь тухайн call ямар ч activity гаргалгүй энэ хугацаанд байвал terminate хийнэ — энэ нь удаан боловч ажиллаж байгаа call биш, жинхэнэ hang-ийг илрүүлэх зориулалттай. Удаан internet connection эсвэл олон reference image ашиглах үед `"no activity for Ns"` failure гарвал `.env` доторх утгыг нэмэгдүүлнэ. `CODEX_IMAGE_TIMEOUT` / `CODEX_TIMEOUT` нь үүнээс тусдаа нийт per-call timeout юм.

**`LLAMA_MODEL_PATH` олдохгүй байна**

Зөвхөн `AI_PROVIDER=llama` үед хамаарна. HuggingFace-аас GGUF татаж аваад `.env` дотор path-ийг тохируулна — эсвэл local model алгасахын тулд `AI_PROVIDER=codex` болгон солино.

**Flux VRAM хүрэхгүй байна**

Зөвхөн `IMAGE_PROVIDER=flux` үед хамаарна. `.env` дотор `FLUX_CPU_OFFLOAD=true` тохируулна (default-оор enabled), `black-forest-labs/FLUX.1-schnell` шиг жижиг model ашиглана, эсвэл `IMAGE_PROVIDER=codex` руу шилжинэ.

**YouTube upload 403 алдаа өгч байна**

OAuth token хугацаа дууссан — `credentials.storage`-г устгаад `make upload`-ийг нэг удаа ажиллуулж дахин authentication хийнэ.

**Pipeline already running (lock file)**

Өмнөх run crash хийгээд lock үлдээсэн байна. `python cli.py stop` эсвэл `rm pipeline.lock` ашиглана.

**Logs**

Бүх module `logs/pipeline.log` файлд (UTF-8 — non-English scene-д асуудалгүй) болон stdout руу log бичнэ. Cron output `logs/cron.log` руу бичигдэнэ. Flutter app-ийн өөрийн log folder-ийг Settings → "Open log folder" хэсгээс нээж болно.

---

## Хөгжүүлэгчийн тухай

**Ажилд авах боломжтой** — end-to-end automation pipeline чиглэлээр мэргэшсэн AI/ML Engineer.

**Энэ project-оор харуулсан ур чадварууд:**

* Олон provider бүхий AI orchestration (local llama.cpp/Flux, OpenAI APIs, Codex CLI)-ийг нэг interface-ийн ард удирдах
* String heuristic биш бодит language identification (fastText) ашиглан scene бүрийн voice/model сонголтыг удирдах
* HuggingFace diffusers + Flux image generation болон `transformers`-д суурилсан ASR fine-tune integration
* FFmpeg media processing pipeline (clips, subtitles, transitions, audio mixing)
* Word-level subtitle alignment-д Whisper speech-to-text ашиглах
* YouTube Data API v3 + OAuth2
* SQLite pipeline state machine болон үе шат бүрийн failure surfacing
* Self-configuring, first-run-aware backend бүхий native Windows desktop app (Flutter)
* Lockfile concurrency control бүхий cron automation
* Zero-config clone-to-run setup

**Холбоо барих: [tuvshin.org@gmail.com](mailto:tuvshin.org@gmail.com)**

---

## License

MIT License — LICENSE файлыг харна уу.
