from flask import Blueprint

from app.errors import register_errors

sms_callback_blueprint = Blueprint("sms_callback", __name__, url_prefix="/notifications/sms")
register_errors(sms_callback_blueprint)

# TODO SNS SMS delivery receipts delivered here
# This file should likely be deleted, since SNS does not use callback https calls
# Leaving for now to have an example of what jobs MMG did that we may want to replicate in the
# eventual SNS method.

# @sms_callback_blueprint.route('/mmg', methods=['POST'])
# def process_mmg_response():
#     client_name = 'MMG'
#     data = json.loads(request.data)
#     errors = validate_callback_data(data=data,
#                                     fields=['status', 'CID'],
#                                     client_name=client_name)
#     if errors:
#         raise InvalidRequest(errors, status_code=400)

#     status = str(data.get('status'))
#     detailed_status_code = str(data.get('substatus'))

#     provider_reference = data.get('CID')

#     process_sms_client_response.apply_async(
#         [status, provider_reference, client_name, detailed_status_code],
#         queue=QueueNames.SMS_CALLBACKS,
#     )

#     return jsonify(result='success'), 200


def validate_callback_data(data, fields, client_name):
    errors = []
    for f in fields:
        if not str(data.get(f, '')):
            error = "{} callback failed: {} missing".format(client_name, f)
            errors.append(error)
    return errors if len(errors) > 0 else None
