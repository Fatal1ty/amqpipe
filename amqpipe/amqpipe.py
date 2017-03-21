# encoding: utf-8

import argparse
import logging
from os import environ as env
from collections import Iterable

import pika
from twisted.internet import defer, reactor, protocol, task

from .utils import AMQPConnection, asleep


logger = logging.getLogger(__name__)


def default_converter(message):
    return message


def default_action(message):
    return message


class AMQPipe(object):
    def __init__(self, converter=default_converter, action=default_action, init=None, need_publish=True):
        self.parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
        self.args = None
        self.need_publish = need_publish
        if need_publish:
            self.wait_publisher = defer.Deferred()
            self.out_channel = None
        self.converter = converter
        self.action = action
        self.init = init

    @defer.inlineCallbacks
    def connect(self, host, port, vhost, user, password):
        credentials = pika.PlainCredentials(user, password)
        parameters = pika.ConnectionParameters(virtual_host=vhost, credentials=credentials)
        cc = protocol.ClientCreator(reactor, AMQPConnection, parameters)
        connection = yield cc.connectTCP(host, port)
        yield connection.ready
        defer.returnValue(connection)

    @defer.inlineCallbacks
    def consume(self, channel, exchange, routing_key, queue):
        yield channel.exchange_declare(exchange=exchange, type=self.args.rq_in_exchange_type, durable=True)
        yield channel.queue_declare(queue=queue, durable=True, auto_delete=False, exclusive=False)
        yield channel.queue_bind(exchange=exchange, queue=queue, routing_key=routing_key)
        yield channel.basic_qos(prefetch_count=self.args.rq_in_qos)
        queue_object, _ = yield channel.basic_consume(queue=queue, no_ack=False)
        channel.my_queue = queue_object
        defer.returnValue(queue_object)

    @defer.inlineCallbacks
    def start_consume(self):
        while True:
            try:
                connection = yield self.connect(
                    self.args.rq_in_host,
                    self.args.rq_in_port,
                    self.args.rq_in_vhost,
                    self.args.rq_in_user,
                    self.args.rq_in_password
                )
            except Exception as e:
                logger.error("Couldn't connect to RabbitMQ server to consume (%s)", e)
                yield asleep(1)
                continue
            try:
                channel = yield connection.channel()
            except Exception as e:
                logger.error("Couldn't open channel to RabbitMQ server to consume (%s)", e)
                yield asleep(1)
                continue
            try:
                queue = yield self.consume(
                    channel,
                    self.args.rq_in_exchange,
                    self.args.rq_in_routing_key,
                    self.args.rq_in_queue
                )
            except Exception as e:
                logger.error("Couldn't consume from queue (%s)", e)
                try:
                    channel.close()
                except:
                    pass
                yield asleep(1)
                continue

            connection.add_connection_errback(queue.close)
            logger.info("Ready to consume messages!")

            while True:
                try:
                    ch, method, properties, body = yield queue.get()
                    reactor.callLater(
                        0, self.on_message,
                        body, properties, channel, method.delivery_tag
                    )
                except Exception as e:
                    logger.error("Disconnect occurred in message consumer (%s)", e)
                    channel.close()
                    break
            yield asleep(5)

    @defer.inlineCallbacks
    def start_publish(self):
        while True:
            disconnect = defer.Deferred()
            try:
                connection = yield self.connect(
                    self.args.rq_out_host,
                    self.args.rq_out_port,
                    self.args.rq_out_vhost,
                    self.args.rq_out_user,
                    self.args.rq_out_password
                )
            except Exception as e:
                logger.error("Couldn't connect to RabbitMQ server to publish (%s)", e)
                yield asleep(1)
                continue
            try:
                self.out_channel = yield connection.channel()
            except Exception as e:
                logger.error("Couldn't open channel to RabbitMQ server to publish (%s)", e)
                yield asleep(1)
                continue
            try:
                yield self.out_channel.exchange_declare(
                    exchange=self.args.rq_out_exchange,
                    type=self.args.rq_out_exchange_type, durable=True
                )
            except Exception as e:
                logger.error("Couldn't declare exchange to publish (%s)", e)
                try:
                    self.out_channel.close()
                except:
                    pass
                yield asleep(1)
                continue

            self.wait_publisher.callback(True)
            connection.add_connection_errback(
                lambda reason: disconnect.callback(reason.getErrorMessage())
            )
            logger.info("Ready to publish messages!")

            reason = yield disconnect
            logger.error("Disconnect occurred in message publisher (%s)", reason)
            yield asleep(5)
            self.wait_publisher = defer.Deferred()

    @defer.inlineCallbacks
    def publish(self, msg):
        yield self.wait_publisher

        exchange = self.args.rq_out_exchange
        routing_key = self.args.rq_out_routing_key_tpl.format(msg)
        try:  # for protobuf messages
            content_type = 'application/protobuf; class="%s"' % msg.DESCRIPTOR.full_name
            serialized = msg.SerializeToString()
            msg_type = msg.DESCRIPTOR.full_name
        except AttributeError:
            content_type = self.args.rq_out_content_type_tpl.format(msg)
            serialized = str(msg)
            msg_type = type(msg)

        logger.debug(
            "Sending %s (exchange=%s, routing_key=%s)",
            msg_type, exchange, routing_key
        )
        result = yield self.out_channel.basic_publish(
            exchange, routing_key, serialized,
            pika.BasicProperties(content_type=content_type, delivery_mode=2)
        )
        defer.returnValue(result)

    @defer.inlineCallbacks
    def on_message(self, body, properties, channel, delivery_tag):
        if self.args.content_type and properties.content_type != self.args.content_type:
            logger.info("Bad content_type (%s), ignoring message.", properties.content_type)
            channel.basic_ack(delivery_tag)
            return

        try:
            message = self.converter(body)
        except:
            logger.warning("Got bad packet!")
            channel.basic_nack(delivery_tag)
            return

        try:
            result = yield self.action(message)
            if self.need_publish:
                if isinstance(result, Iterable):
                    try:
                        yield defer.DeferredList([self.publish(r) for r in result],
                                                 fireOnOneErrback=True, consumeErrors=True)
                    except defer.FirstError as e:
                        e.subFailure.raiseException()
                elif result:
                    yield self.publish(result)
            channel.basic_ack(delivery_tag)
        except Exception as e:
            logger.warning('Sending NACK due to %s: %s', type(e).__name__, str(e))
            channel.basic_nack(delivery_tag)

    @defer.inlineCallbacks
    def main(self):
        if self.init:
            logger.info('Initialization...')
            yield self.init(self.args)
        logger.info('Connecting to RabbitMQ server to consume...')
        reactor.callLater(0, self.start_consume)
        if self.need_publish:
            logger.info('Connecting to RabbitMQ server to publish...')
            reactor.callLater(0, self.start_publish)

    def _parse_args(self):
        self.parser.add_argument("--content-type", help="Expected content-type")

        rq_in_args = self.parser.add_argument_group(
            "Input RabbitMQ",
            "Connection parameters for input RabbitMQ to consume messages"
        )
        rq_in_args.add_argument("--rq-in-qos", default=0, type=int, help="prefetch_count for input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-host", default="127.0.0.1", help="hostname of input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-port", default=5672, type=int, help="port of input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-user", default="guest", help="username for input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-password", default="guest", help="password for input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-vhost", default="/", help="virtual host of input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-exchange", required=True, help="exchange for input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-exchange-type", default='topic',
                                help="exchange type for input RabbitMQ server")
        rq_in_args.add_argument("--rq-in-routing-key", required=True, help="routing key for input RabbitMQ exchange")
        rq_in_args.add_argument("--rq-in-queue", required=True, help="name of input RabbitMQ queue to consume")

        if self.need_publish:
            rq_out_args = self.parser.add_argument_group(
                "Output RabbitMQ",
                "Connection parameters for output RabbitMQ to publish messages"
            )
            rq_out_args.add_argument("--rq-out-host", default="127.0.0.1", help="hostname of output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-port", default=5672, type=int, help="port of output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-user", default="guest", help="username for output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-password", default="guest", help="password for output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-vhost", default="/", help="virtual host of output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-exchange", required=True, help="exchange for output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-exchange-type", default='topic',
                                     help="exchange type for output RabbitMQ server")
            rq_out_args.add_argument("--rq-out-routing-key-tpl", required=True,
                                     help="routing key template of messages sent to output RabbitMQ exchange")
            rq_out_args.add_argument("--rq-out-content-type-tpl", default="text/plain",
                                     help="content type template of messages not in protobuf sent to output RabbitMQ exchange")

        self.parser.add_argument("--log-file", help="name of log file (if missed - write logs to stderr)")
        self.parser.add_argument("--log-level", default='INFO',
                                 choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                                 help="logging level")

        return self.parser.parse_args()

    def _setup_logger(self):
        log_level = getattr(logging, self.args.log_level)

        root_logger = logging.getLogger()

        if self.args.log_file:
            log_handler = logging.handlers.TimedRotatingFileHandler(self.args.log_file)
            log_handler.setFormatter(logging.Formatter(
                '[%(asctime)s] %(levelname)8s %(funcName)s:%(lineno)d %(message)s'
            ))
            log_handler.setLevel(log_level)
            root_logger.addHandler(log_handler)
            root_logger.setLevel(log_level)
        else:
            logging.basicConfig(
                format='[%(asctime)s] %(levelname)8s %(module)6s:%(lineno)03d %(message)s',
                level=log_level
            )
            if 'xterm' in env.get('TERM', ''):
                try:
                    from colorlog import ColoredFormatter
                except ImportError:
                    return

                root_logger.handlers[0].setFormatter(ColoredFormatter(
                    (
                        '%(bold_blue)s[%(asctime)s]%(reset)s '
                        '%(log_color)s%(levelname)-8s%(reset)s '
                        '%(message)s'
                    ),
                    reset=True,
                    log_colors={
                        'DEBUG': 'bold_cyan',
                        'INFO': 'bold_green',
                        'WARNING': 'bold_yellow',
                        'ERROR': 'bold_red',
                        'CRITICAL': 'bold_red,bg_white',
                    },
                    secondary_log_colors={
                        'message': {
                            'ERROR': 'red',
                            'CRITICAL': 'red'
                        }
                    },
                    style='%'
                ))

    def run(self):
        self.args = self._parse_args()
        self._setup_logger()
        d = task.deferLater(reactor, 0, self.main)

        def on_error(e):
            logger.error(e.getErrorMessage())
            reactor.stop()

        d.addErrback(on_error)
        reactor.run()
