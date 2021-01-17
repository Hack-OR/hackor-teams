#!/usr/bin/env python3
# XXX: this file is kind of a hack, but this discord bot is only gonna be used 
# once, so I don't think it matters much.

import yaml
import os

db = {
    'users': {}
}


def read() -> None:
    try:
        with open('db.yml', 'r') as f:
            db = yaml.safe_load(f)
    except FileNotFoundError:
        # the file will be created next write
        pass


def write() -> None:
    # write to different file THEN move to avoid potential race condition
    # between opening and writing to files
    with open('db.yml.tmp', 'w') as f:
        f.write(yaml.dump(db))
    
    os.rename('db.yml.tmp', 'db.yml')

