# Back-end web service routines for the functional curation website

import json
import os


config = json.load(open(os.path.join(os.path.dirname(__file__), 'config.json')))
user_queue_map = json.load(open(os.path.join(os.path.dirname(__file__), 'usermap.json')))
checked_queues = set(['default', 'admin'])


def GetQueue(user, isAdmin):
    """Determine which Celery queue to use for a task, based on the user submitting it."""
    if isAdmin:
        queue = 'admin'
    else:
        queue = user_queue_map.get(user, 'default')
        # Check that the queue has (or at least, had!) consumers and fall back to default if not
        if queue not in checked_queues:
            from .tasks import app
            if queue not in [q['name']
                             for l in app.control.inspect().active_queues().values()
                             for q in l]:
                queue = 'default'
            else:
                checked_queues.add(queue)
    return queue


def ScheduleExperiment(
        callbackUrl, signature, modelUrl, protoUrl, user='', isAdmin=False, **kwargs):
    """Schedule a new experiment for execution."""
    from .tasks import CheckExperiment
    # Submit the job
    args = (
        callbackUrl,
        signature,
        modelUrl,
        protoUrl,
    )
    result = CheckExperiment.apply_async(args, kwargs, queue=GetQueue(user, isAdmin))
    # Tell web interface that the call was successful
    print(signature, "succ", result.task_id)


def CancelExperiment(taskId):
    """Revoke or terminate an already submitted experiment."""
    import signal
    from .tasks import app
    app.control.revoke(taskId, terminate=True, signal=signal.SIGUSR1)


def GetProtocolInterface(callbackUrl, signature, protoUrl):
    """Get the ontology terms forming the interface for a protocol."""
    from .tasks import GetProtocolInterface
    GetProtocolInterface.apply_async((callbackUrl, signature, protoUrl), queue=GetQueue('', True))


def GetModelInterface(callbackUrl, signature, modelUrl):
    """Get the ontology terms forming the interface for a model."""
    from .tasks import GetModelInterface
    GetModelInterface.apply_async((callbackUrl, signature, modelUrl), queue=GetQueue('', True))
