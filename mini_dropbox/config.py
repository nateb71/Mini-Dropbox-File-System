CONTROL_PORT    = 5000   # port for command messages (LIST, UPLOAD, DOWNLOAD)
UPLOAD_PORT     = 5001   # port for receiving file data from clients
DOWNLOAD_PORT   = 5002   # port for sending file data to clients
DISCOVERY_PORT  = 5003   # UDP broadcast port for server auto-discovery
BUFFER_SIZE     = 4096   # how many bytes to read/write at a time
STORAGE_DIR     = "server_storage"  # root folder where all files are stored
