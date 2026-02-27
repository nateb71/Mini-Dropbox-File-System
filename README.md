Mini Dropbox – Distributed File Synchronization System
Overview

Mini Dropbox is a simplified client-server file synchronization system developed for an Introduction to Computer Networks course. The application demonstrates socket programming, process-to-process communication, and reliable file transfer using TCP.

The system allows multiple clients to connect to a centralized server to upload files, download files, and retrieve a list of stored files. All communication is handled using custom socket-based protocols written in Python.

This project is designed to highlight networking fundamentals rather than user interface complexity.

Architecture

The system follows a client-server model:

Server

Listens for incoming TCP connections

Handles multiple clients using threading

Stores uploaded files persistently on disk

Responds to file listing, upload, and download requests

Client

Connects to the server using TCP sockets

Provides a command-line interface

Reads files from a local directory for upload

Writes downloaded files to a local directory

Communication is divided into:

A control connection for commands (LIST, UPLOAD, DOWNLOAD)

Dedicated file transfer connections for sending and receiving file data

Features

TCP socket programming using Python

Process-to-process communication

Multiple concurrent client connections

File upload and download functionality

Server-side persistent file storage

Command-line interface

Basic error handling and file validation

Technologies Used

Python 3

Python socket library

Threading for concurrent connections

Local file system storage
