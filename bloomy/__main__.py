import asyncio
import logging


async def main():
    from .bloomy import Bloomy

    loop = asyncio.get_running_loop()
    app = Bloomy(loop=loop)
    app.setup_loggers(__package__, app.plugin_manager.plugins_dir.parts[0])

    await app.init()
    try:
        await app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.getLogger(__package__).exception("Stopped app.run", exc_info=e)
    finally:
        try:
            await app.cleanup()
        except Exception as e:
            logging.getLogger(__package__).exception("Exception in app.cleanup", exc_info=e)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
