for port in {8888..8907}; do
  python3 COMP3221_BlockchainNode.py $port nodes.txt > $port.txt &
done
