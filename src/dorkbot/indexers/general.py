def populate_general_options(module_group):
    module_group.add_argument("--retries", type=int, default=10,
                              help="number of times to retry fetching results on error")
    module_group.add_argument("--threads", type=int, default=10,
                              help="number of concurrent requests to wayback.org")
