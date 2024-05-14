for port in {8010..8011}; do
  lsof -nP -tiTCP:$port -sTCP:LISTEN | xargs kill
done
