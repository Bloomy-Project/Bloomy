import asyncio

if __name__ == '__main__':
    from .bloomy import Bloomy

    loop = asyncio.new_event_loop()
    main = Bloomy(loop=loop)
    main.setup_loggers(__package__, main.plugins_dir.parts[0])

    try:
        loop.run_until_complete(main.start())
    except KeyboardInterrupt:
        pass
