| scenario | mode | runs | recovered | MTTD mean | MTTD median | MTTR mean | MTTR median | MTTR max | fixed by |
|---|---|---|---|---|---|---|---|---|---|
| kill | auto | 10 | 10/10 | - | - | 0.7 s | 0.0 s | 1.8 s | kubernetes itself 4×, no visible downtime 6× |
| hang | auto | 10 | 10/10 | 18.5 s | 18.5 s | 18.0 s | 18.3 s | 18.7 s | k8s livenessProbe 8×, kubernetes itself 2× |
| latency | auto | 10 | 10/10 | 25.5 s | 26.1 s | 27.4 s | 27.5 s | 31.0 s | restart 10× |
| disk | auto | 10 | 10/10 | 18.5 s | 17.7 s | 19.9 s | 19.2 s | 23.9 s | cleanup_disk 10× |
| bad_deploy | auto | 10 | 10/10 | 21.7 s | 22.2 s | 23.3 s | 23.9 s | 24.6 s | rollback 10× |
