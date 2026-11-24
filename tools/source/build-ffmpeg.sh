#!/bin/bash
# Builds tools\ffmpeg.exe and tools\ffprobe.exe from the source archives beside this script:
# FFmpeg 9.0.2 (LGPL 2.1+) with LAME 3.100 (LGPL 2.1+), audio only, no other external libraries.
# Run in an MSYS2 MINGW64 shell with: pacman -S make diffutils mingw-w64-x86_64-gcc mingw-w64-x86_64-nasm
#   cd "<this folder>" && ./build-ffmpeg.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$SRC/build}"
PREFIX="$WORK/prefix"
mkdir -p "$WORK"
cd "$WORK"

tar xzf "$SRC/lame-3.100.tar.gz"
cd lame-3.100
./configure --prefix="$PREFIX" --host=x86_64-w64-mingw32 --disable-shared --enable-static \
    --disable-frontend --disable-decoder --disable-gtktest
make -j"$(nproc)" && make install
cd ..

tar xJf "$SRC/ffmpeg-9.0.2.tar.xz"
cd ffmpeg-9.0.2
./configure --prefix="$PREFIX" --arch=x86_64 --target-os=mingw32 \
    --disable-shared --enable-static --disable-autodetect --disable-debug --disable-doc --disable-network \
    --disable-everything --disable-ffplay --enable-ffmpeg --enable-ffprobe \
    --enable-libmp3lame --enable-swresample \
    --enable-protocol=file,pipe \
    --enable-demuxer=wav,mp3,ogg,flac,aiff \
    --enable-muxer=wav,mp3 \
    --enable-parser=mpegaudio,flac,vorbis \
    --enable-decoder='pcm*,adpcm*,mp1*,mp2*,mp3*,gsm_ms,vorbis,flac' \
    --enable-encoder=pcm_s16le,libmp3lame \
    --enable-filter=aresample,aformat,anull,atrim,asetpts \
    --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib -static" \
    --pkg-config-flags=--static
make -j"$(nproc)"
strip ffmpeg.exe ffprobe.exe
cp ffmpeg.exe ffprobe.exe "$WORK/"
echo "built: $WORK/ffmpeg.exe $WORK/ffprobe.exe"
