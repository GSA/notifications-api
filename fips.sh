
#!/bin/zsh

# clone from openssl
git clone https://github.com/openssl/openssl.git
cd openssl

# get 3.0.8, the latest fips compliant version
git checkout 31157bc


mkdir build
cd build

# Configure for Ken's laptop architecture, plus enable FIPS (!!) plus specify output folder
../Configure darwin64-x86_64 enable-fips --debug --prefix=/Users/kkehl/Projects/fips/openssl/install
make
make install

# Check the version.  There should be comments about FIPS enabled as well
/Users/kkehl/Projects/fips/openssl/install/bin/openssl version
