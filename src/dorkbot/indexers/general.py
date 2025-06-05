def populate_general_options(module_group):
    module_group.add_argument("--http-retries", type=int, default=2,
                              help="number of times to retry fetching results on error")
    module_group.add_argument("--threads", type=int, default=1,
                              help="number of concurrent requests to wayback.org")
