#!/usr/bin/env bash

set -euo pipefail

echo "Initializing..."
build_date="20211017"
build_time="1616"
declare -A os=(["Darwin"]="apple-darwin" ["Linux"]='unknown-linux-gnu')
os="${os[`uname`]}"
declare -A arch=(["arm64"]="aarch64" ["x86_64"]="x86_64")
arch="${arch[`uname -m`]}"
tar_file="cpython-3.10.0-${arch}-${os}-pgo+lto-${build_date}T${build_time}.tar"
tarz_file="${tar_file}.zst"
url="https://github.com/indygreg/python-build-standalone/releases/download/${build_date}/${tarz_file}"

cd dist
test -f build.log && rm build.log
test ! -f "${tarz_file}" && echo "Fetching portable python build from indygreg/python-build-standalone" && wget "${url}" &>> build.log
test ! -f "${tar_file}" && echo "Decompressing zstd archive..." && zstd -d "${tarz_file}" &>> build.log

echo "Unpacking decompressed tar file..."
tar -xvf "${tar_file}" &>> build.log
test -d utsc-tools && rm -r utsc-tools

echo "Prepping utsc-tools python distribution..."
mkdir utsc-tools
mv python/install/* utsc-tools/
cp ../scripts/fix-shebangs.py utsc-tools/bin/

echo "installing 'utsc' python package into distribution..."
utsc-tools/bin/pip install utsc &>> build.log
utsc-tools/bin/fix-shebangs.py
echo "Packing utsc-tools distribution into gzip-compressed archive..."
tar -czvf "utsc-tools-$(uname)-$(uname -m).tar.gz" utsc-tools/ &>> build.log

echo "Done!"
