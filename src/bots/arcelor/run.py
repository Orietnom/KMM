from src.bots.arcelor import publisher, worker

if __name__ == '__main__':
    try:
        publisher.Main().start_process()
        worker.run()
    except:
        pass
