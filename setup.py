#!/usr/bin/env python

from distutils.core import setup

setup(
    name='amqpipe',
    version='0.1.5',
    description='Twisted based pipeline framework for AMQP',
    platforms="all",
    classifiers=[
        'Environment :: Console',
        'Programming Language :: Python',
    ],
    license='MIT',
    author='Alexander Tikhonov',
    author_email='random.gauss@gmail.com',
    url='https://github.com/Fatal1ty/amqpipe',
    packages=['amqpipe'],
    install_requires=[
        'twisted',
        'pika',
        'colorlog'
    ]
)
