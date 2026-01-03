"""
Временный способ выполнять задачи без Celery: синхронный вызов.
Usage:
  python scripts/run_jobs_locally.py index  <dataset_id>
  python scripts/run_jobs_locally.py annotate <dataset_id> <level>
"""
import sys
from backend.app.tasks.tasks import index_dataset, annotate_dataset

def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "index":
        dataset_id = int(sys.argv[2])
        print(index_dataset(dataset_id))
    elif cmd == "annotate":
        dataset_id = int(sys.argv[2]); level = sys.argv[3]
        print(annotate_dataset(dataset_id, level))
    else:
        print("unknown cmd")

if __name__ == "__main__":
    main()
