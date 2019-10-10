# The settings in this file shouldn't need to be changed on different installations.
# See /etc/default/celeryd for node-specific configuration.

task_serializer = 'json'
accept_content = ['json']
timezone = 'Europe/London'
enable_utc = True

# Default broker to contact (if not overridden in CELERYD_OPTS)
broker_url = 'amqp://guest@localhost'

# Default queue name to use
task_default_queue = "default"

# We expect to have few tasks, but long running, so don't reserve more than you're working on
# (this works well combined with the -Ofair option to the workers)
worker_prefetch_multiplier = 1
task_acks_late = True
# Since tasks are long-running, we want to know if they are actually running
task_track_started = True

# Just in case, restart workers once they've run this many jobs
worker_max_tasks_per_child = 50

task_soft_time_limit = 60 * 60 * 15  # 15 hours
# TODO: Check default time limits; should probably differ for admin & normal users
# can set with decorator: @app.task(soft_time_limit=) or config task_soft_time_limit or as soft_time_limit option to apply_async.
# Also need to look into creating per-user queues dynamically - tricky bit is getting a worker to consume them!

# We need a result backend to track task status.
# However we don't need to store results, since the tasks will callback to the front-end.
result_backend = 'amqp'
task_ignore_result = True

# We don't make use of rate limiting, so turn it off for a performance boost
worker_disable_rate_limits = True

# How many times to try calling back to the front-end before giving up.
# We employ an exponential backoff on attempts, so delay 1, 2, 4, etc. minutes.
WEB_LAB_MAX_CALLBACK_ATTEMPTS = 3
