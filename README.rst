AMQPipe
=======

.. image:: https://img.shields.io/pypi/dm/amqpipe.svg?maxAge=2592000
   :target: https://pypi.python.org/pypi/amqpipe

.. image:: https://img.shields.io/pypi/v/amqpipe.svg?maxAge=2592000
   :target: https://pypi.python.org/pypi/amqpipe

.. image:: https://img.shields.io/pypi/pyversions/amqpipe.svg?maxAge=2592000
   :target: https://pypi.python.org/pypi/amqpipe

.. image:: https://img.shields.io/badge/license-MIT-blue.svg?maxAge=2592000
   :target: https://raw.githubusercontent.com/Fatal1ty/amqpipe/master/LICENSE

Twisted based pipeline framework for AMQP. It allow you to create fast
asynchronous services which follow ideology:

-  get message from queue
-  doing something with message
-  publish some result

Installation
------------

Install via pip:

::

        pip install amqpipe

Basic usage
-----------

The minimal module based on AMQPipe is:

.. code:: python

    from amqpipe import AMQPipe

    pipe = AMQPipe()
    pipe.run()

It will simply get all messages from one RabbitMQ queue and publish them
to other RabbitMQ exchange.

Now we define some action on messages:

.. code:: python

    import hashlib
    from amqpipe import AMQPipe

    def action(message):
        return hashlib.md5(message).hexdigest()

    pipe = AMQPipe(action=action)
    pipe.run()

It will publish md5 checksum for every message as result.

If messages in input queue are in predefined format then you can define
converter-function:

.. code:: python

    import hashlib
    from amqpipe import AMQPipe

    def converter(message):
        return message['text']

    def action(text):
        return hashlib.md5(text).hexdigest()

    pipe = AMQPipe(converter=converter, action=action)
    pipe.run()

You can define service-specific arguments:

.. code:: python

    import hashlib
    from amqpipe import AMQPipe

    class Processor:
        def set_field(self, field):
            self.field = field

    processor = Processor()

    def init(args):
        processor.set_field(args.field)

    def converter(message):
        return message.get(processor.field)

    def action(text):
        return hashlib.md5(text).hexdigest()

    pipe = AMQPipe(converter, action, init)
    pipe.parser.add_argument('--field', default='text', help='Field name for retrieving message value')
    pipe.run()

You can connect to database in ``init`` function or do some other things
for initialization.

If your action returns Deferred then result would be published to
RabbitMQ when this Deferred will be resolved:

.. code:: python

    import logging
    from twisted.internet import defer
    from amqpipe import AMQPipe

    logger = logging.getLogger(__name__)

    class Processor:
        def set_field(self, field):
            self.field = field

    processor = Processor()

    def init(args):
        connect_to_db()
        ...

    def converter(message):
        return message.get(processor.field)

    @defer.inlineCallbacks
    def action(text):
        result = yield db_query(text)
        logger.info('Get from db: %s', result)
        defer.returnValue(result)

    pipe = AMQPipe(converter, action, init)
    pipe.parser.add_argument('--field', default='text', help='Field name for retrieving message value')
    pipe.run()

Init function may return Deferred too.