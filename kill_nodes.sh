for port in {8888..8907}; do
  lsof -nP -tiTCP:$port -sTCP:LISTEN | xargs kill
done
