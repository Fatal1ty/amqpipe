import twisted.internet.error
from twisted.internet import defer, reactor
from pika.adapters import twisted_connection


def asleep(seconds):
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


class AMQPConnection(twisted_connection.TwistedProtocolConnection):
    def __init__(self, parameters, connection_errback=None):
        super(AMQPConnection, self).__init__(parameters)
        self.connection_errback = connection_errback

    def connectionLost(self, reason):
        super(AMQPConnection, self).connectionLost(reason)
        if self.connection_errback:
            self.connection_errback(reason)

    def connectionFailed(self, connection_unused, error_message=None):
        super(AMQPConnection, self).connectionFailed(connection_unused, error_message)
        if self.connection_errback:
            self.connection_errback(twisted.internet.error.ConnectionLost(error_message))

    def add_connection_errback(self, method):
        self.connection_errback = method
