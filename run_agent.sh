if test -d langchain_trader; then
  echo "Removing previous agent build"
  rm -r langchain_trader
fi

find . -empty -type d -delete  # remove empty directories to avoid wrong hashes
autonomy packages lock
autonomy fetch --local --agent valory/langchain_trader
python scripts/aea-config-replace.py
cd langchain_trader
cp $PWD/../ethereum_private_key.txt .
autonomy add-key ethereum ethereum_private_key.txt
autonomy issue-certificates
aea -s run