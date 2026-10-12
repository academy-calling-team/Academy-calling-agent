"""Transport outcomes shared by the adapter and durable dispatcher."""
class WorkerRejected(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        # Never retain a remote error body (it may contain private request data).
        super().__init__(f'Worker rejected request: HTTP {status_code}')

class WorkerProtocolError(Exception):
    """Unexpected response requires review, not blind retransmission."""
