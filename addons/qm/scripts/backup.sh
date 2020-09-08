#! /bin/bash

cur_time=$(date '+%Y-%m-%d')
sevendays_time=$(date -d -7days '+%Y-%m-%d')

pushd /root/backup
rm -rf vgroups.*.sql
rm -rf vgroups.$sevendays_time.tar.gz
pg_dump -h localhost -U vgroups vgroups > vgroups.$cur_time.sql
tar zcvf vgroups.$cur_time.tar.gz *.sql
rm -rf vgroups.*.sql
popd