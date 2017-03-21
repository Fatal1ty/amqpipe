#!/usr/bin/env python

from setuptools import setup

setup(
    name='amqpipe',
    version='0.2.7',
    description='Twisted based pipeline framework for AMQP',
    long_description=open('README.rst').read(),
    platforms='all',
    classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Console',
          'Framework :: Twisted',
          'License :: OSI Approved :: MIT License',
          'Natural Language :: English',
          'Operating System :: MacOS :: MacOS X',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: Implementation :: CPython',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: System',
          'Topic :: System :: Software Distribution',
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
