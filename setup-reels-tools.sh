#!/usr/bin/env bash
# 릴스 편집 도구 설치 스크립트 (macOS)
# 사용법: bash setup-reels-tools.sh
set -euo pipefail

MODEL_NAME="ggml-large-v3-turbo-q5_0.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_NAME}"
MODEL_DIR="$HOME/.cache/whisper"
VENV_DIR="$HOME/.pycapcut"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "이 스크립트는 macOS용입니다." >&2
  exit 1
fi

# 1. Homebrew (설치 중 맥 비밀번호를 물어보면 직접 입력하세요)
if ! command -v brew >/dev/null 2>&1; then
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$p" ]] && eval "$("$p" shellenv)"
  done
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "==> Homebrew 설치 (맥 비밀번호 입력이 필요합니다)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$p" ]] && eval "$("$p" shellenv)" && BREW_BIN="$p"
  done
  # 새 터미널에서도 brew를 쓸 수 있도록 PATH 등록
  if ! grep -q 'brew shellenv' "$HOME/.zprofile" 2>/dev/null; then
    echo "eval \"\$(${BREW_BIN} shellenv)\"" >> "$HOME/.zprofile"
  fi
fi

# 2. yt-dlp, ffmpeg, whisper-cpp
echo "==> brew 패키지 설치"
brew install yt-dlp ffmpeg whisper-cpp python

# 3. whisper 모델
echo "==> whisper 모델 다운로드"
mkdir -p "$MODEL_DIR"
if [[ ! -s "$MODEL_DIR/$MODEL_NAME" ]]; then
  curl -L --fail -C - -o "$MODEL_DIR/$MODEL_NAME" "$MODEL_URL"
else
  echo "    이미 있음: $MODEL_DIR/$MODEL_NAME"
fi

# 4. pycapcut 가상환경
echo "==> pycapcut 가상환경 생성"
PY="$(brew --prefix)/bin/python3"
[[ -x "$PY" ]] || PY="python3"
[[ -d "$VENV_DIR" ]] || "$PY" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install pycapcut

# 6. 버전 확인
echo
echo "==> 설치된 버전"
echo "brew:        $(brew --version | head -1)"
echo "yt-dlp:      $(yt-dlp --version)"
echo "ffmpeg:      $(ffmpeg -version | head -1)"
echo "whisper-cpp: $(brew list --versions whisper-cpp)"
echo "모델:        $(ls -lh "$MODEL_DIR/$MODEL_NAME" | awk '{print $5, $9}')"
echo "python:      $("$VENV_DIR/bin/python" --version)"
echo "pycapcut:    $("$VENV_DIR/bin/pip" show pycapcut | awk '/^Version/{print $2}')"
echo
echo "설치 끝!"
