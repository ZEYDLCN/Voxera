from apps.worker.queue import CeleryImportJobQueue
from voxera.api.app import create_app

app = create_app(import_job_queue=CeleryImportJobQueue())

