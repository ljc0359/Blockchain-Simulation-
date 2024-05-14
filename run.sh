for port in {8010..8011}; do
  python3 COMP3221_BlockchainNode.py $port nodes.txt > $port.txt &
done
