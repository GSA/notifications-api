from os import path

from flask import Blueprint, current_app, send_file

docs = Blueprint('docs', __name__, url_prefix='/docs')

@docs.route('/openapi.yml', methods=['GET'])
def send_openapi():
    openapi_schema = path.join(current_app.root_path, '../docs/openapi.yml')
    return send_file(openapi_schema, mimetype='text/yaml'), 200
