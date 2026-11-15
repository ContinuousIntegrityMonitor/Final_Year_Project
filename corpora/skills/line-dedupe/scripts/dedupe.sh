# Write the unique lines of one file to $HOME/deduped.txt and report the count.
sort -u "$1" > "$HOME/deduped.txt"
wc -l < "$HOME/deduped.txt"
