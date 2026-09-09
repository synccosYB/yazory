import os
import app_original as _app

# Keep the established application intact while extending the supporter
# relationship choices with a distinct shul-friend option.
if 'Shul friend' not in _app.RELATIONSHIPS:
    insert_at = _app.RELATIONSHIPS.index('Friend') if 'Friend' in _app.RELATIONSHIPS else len(_app.RELATIONSHIPS)
    _app.RELATIONSHIPS.insert(insert_at, 'Shul friend')

from app_original import *  # noqa: F401,F403,E402

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
