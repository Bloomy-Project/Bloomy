import asyncio
import logging

if __name__ == '__main__':
    from .bloomy import Bloomy
    from ._logger import setup_loggers

    loop = asyncio.new_event_loop()
    main = Bloomy(loop=loop)
    setup_loggers(__package__, logging.DEBUG)
    setup_loggers(main.plugins_dir.stem, logging.DEBUG)

    try:
        loop.run_until_complete(main.start())
    except KeyboardInterrupt:
        pass
