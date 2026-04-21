from routes.auth      import auth_bp
from routes.dashboard import dashboard_bp
from routes.clients   import clients_bp
from routes.routers   import routers_bp
from routes.onboard   import onboard_bp
from routes.settings  import settings_bp

blueprints = [auth_bp, dashboard_bp, clients_bp, routers_bp, onboard_bp, settings_bp]
