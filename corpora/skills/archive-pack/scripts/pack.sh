# Pack docs/ into $HOME/docs.tar.gz and list what went in.
tar -czf "$HOME/docs.tar.gz" docs
tar -tzf "$HOME/docs.tar.gz" | sort
