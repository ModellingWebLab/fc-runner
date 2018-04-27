# The settings in this file shouldn't need to be changed on different installations.
# See /etc/default/celeryd for node-specific configuration.

CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT=['json']
CELERY_TIMEZONE = 'Europe/London'
CELERY_ENABLE_UTC = True

# Default broker to contact (if not overridden in CELERYD_OPTS)
BROKER_URL = 'amqp://guest@localhost'

# Default queue name to use
CELERY_DEFAULT_QUEUE="default"

# We expect to have few tasks, but long running, so don't reserve more than you're working on
# (this works well combined with the -Ofair option to the workers)
CELERYD_PREFETCH_MULTIPLIER = 1
CELERY_ACKS_LATE = True
# Since tasks are long-running, we want to know if they are actually running
CELERY_TRACK_STARTED = True

# Just in case, restart workers once they've run this many jobs
CELERYD_MAX_TASKS_PER_CHILD = 50

CELERYD_TASK_SOFT_TIME_LIMIT = 60 * 60 * 15  # 15 hours
# TODO: Check default time limits; should probably differ for admin & normal users
# can set with decorator: @app.task(soft_time_limit=) or config CELERYD_TASK_SOFT_TIME_LIMIT or as soft_time_limit option to apply_async.
# Also need to look into creating per-user queues dynamically - tricky bit is getting a worker to consume them!

# We need a result backend to track task status.
# However we don't need to store results, since the tasks will callback to the front-end.
CELERY_RESULT_BACKEND = 'amqp'
CELERY_IGNORE_RESULT = True

# We don't make use of rate limiting, so turn it off for a performance boost
CELERY_DISABLE_RATE_LIMITS = True

# How many times to try calling back to the front-end before giving up.
# We employ an exponential backoff on attempts, so delay 1, 2, 4, etc. minutes.
WEB_LAB_MAX_CALLBACK_ATTEMPTS = 3
