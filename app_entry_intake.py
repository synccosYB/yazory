import app_entry as base
from application_intake import install


def create_app(test_config=None):
    app = base.create_app(test_config)
    install(app)
    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=5000)
