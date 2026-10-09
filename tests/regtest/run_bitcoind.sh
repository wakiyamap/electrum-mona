#!/usr/bin/env bash
export HOME=~
set -eux pipefail
mkdir -p ~/.monacoin
cat > ~/.monacoin/monacoin.conf <<EOF
regtest=1
txindex=1
printtoconsole=1
rpcuser=doggman
rpcpassword=donkey
rpcallowip=127.0.0.1
zmqpubrawblock=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28333
fallbackfee=0.0002
[regtest]
rpcbind=0.0.0.0
rpcport=19443
EOF
rm -rf ~/.monacoin/regtest
monacoind -regtest &
sleep 6
# monacoin-cli createwallet test_wallet
addr=$(monacoin-cli getnewaddress)
monacoin-cli generatetoaddress 150 $addr
tail -f ~/.monacoin/regtest/debug.log
