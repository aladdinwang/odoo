#! /bin/bash

cur_time=$(date '+%Y-%m-%d')
sevendays_time=$(date -d -7days '+%Y-%m-%d')
export PGPASSWORD=vgroups
rm -rf /root/backup/vgroups.$sevendays_time.tar.gz
pg_dump -U vgroups -d vgroups >"/root/backup/vgroups.$cur_time.dmp"
tar zcvf "/root/backup/vgroups.$cur_time.tar.gz" *.dmp
rm -rf pgsql-backup.*.dmp
