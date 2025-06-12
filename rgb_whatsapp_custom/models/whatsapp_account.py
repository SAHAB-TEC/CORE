import logging
import mimetypes

from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from odoo import tools, _
from odoo import api, Command, fields, models, tools, _
from odoo.addons.whatsapp.tools.whatsapp_api import WhatsAppApi
from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation
from odoo.tools import plaintext2html
import phonenumbers
from phonenumbers import geocoder

_logger = logging.getLogger(__name__)


class WhatsappAccount(models.Model):
    _inherit = 'whatsapp.account'

    # supervisor_ids = fields.Many2many('res.users', "whatsapp_account_supervisor_ids_rel", string='Supervisors')
    def _process_messages(self, value):
        """
            This method is used for processing messages with the values received via webhook.
            If any whatsapp message template has been sent from this account then it will find the active channel or
            create new channel with last template message sent to that number and post message in that channel.
            And if channel is not found then it will create new channel with notify user set in account and post message.
            Supported Messages
             => Text Message
             => Attachment Message with caption
             => Location Message
             => Contact Message
             => Message Reactions
        """
        if 'messages' not in value and value.get('whatsapp_business_api_data', {}).get('messages'):
            value = value['whatsapp_business_api_data']

        wa_api = WhatsAppApi(self)

        for messages in value.get('messages', []):
            parent_id = False
            channel = False
            sender_name = value.get('contacts', [{}])[0].get('profile', {}).get('name')
            sender_mobile = messages['from']
            message_type = messages['type']
            if 'context' in messages and messages['context'].get('id'):
                parent_whatsapp_message = self.env['whatsapp.message'].sudo().search([('msg_uid', '=', messages['context']['id'])])
                if parent_whatsapp_message:
                    parent_id = parent_whatsapp_message.mail_message_id
                if parent_id:
                    channel = self.env['discuss.channel'].sudo().search([('message_ids', 'in', parent_id.id)], limit=1)

            if not channel:
                channel = self._find_active_channel(sender_mobile, sender_name=sender_name, create_if_not_found=True)
            kwargs = {
                'message_type': 'whatsapp_message',
                'author_id': channel.whatsapp_partner_id.id,
                'subtype_xmlid': 'mail.mt_comment',
                'parent_id': parent_id.id if parent_id else None,
            }

            if messages.get('button'):
                if messages['button'].get('payload') in ['ايقاف']:
                    # stop receiving messages
                    sender_partner = self.env['res.partner'].sudo().search(['|',('mobile', '=', sender_mobile),('phone', '=', sender_mobile)], limit=1)
                    attendee_id = channel.attendee_id
                    if attendee_id and sender_partner:
                        if channel.attenee_type == 'reminder':
                            attendee_id.sudo().write({
                                'stop_reminder': True,
                            })
                        if channel.attenee_type == 'reminder_desc':
                            attendee_id.sudo().write({
                                'stop_reminder_desc': True,
                            })


            if message_type == 'text':
                kwargs['body'] = plaintext2html(messages['text']['body'])
            elif message_type == 'button':
                kwargs['body'] = messages['button']['text']
            elif message_type in ('document', 'image', 'audio', 'video', 'sticker'):
                filename = messages[message_type].get('filename')
                is_voice = messages[message_type].get('voice')
                mime_type = messages[message_type].get('mime_type')
                caption = messages[message_type].get('caption')
                datas = wa_api._get_whatsapp_document(messages[message_type]['id'])
                if not filename:
                    extension = mimetypes.guess_extension(mime_type) or ''
                    filename = message_type + extension
                kwargs['attachments'] = [(filename, datas, {'voice': is_voice})]
                if caption:
                    kwargs['body'] = plaintext2html(caption)
            elif message_type == 'location':
                url = Markup("https://maps.google.com/maps?q={latitude},{longitude}").format(
                    latitude=messages['location']['latitude'], longitude=messages['location']['longitude'])
                body = Markup('<a target="_blank" href="{url}"> <i class="fa fa-map-marker"/> {location_string} </a>').format(
                    url=url, location_string=_("Location"))
                if messages['location'].get('name'):
                    body += Markup("<br/>{location_name}").format(location_name=messages['location']['name'])
                if messages['location'].get('address'):
                    body += Markup("<br/>{location_address}").format(location_address=messages['location']['address'])
                kwargs['body'] = body
            elif message_type == 'contacts':
                body = ""
                for contact in messages['contacts']:
                    body += Markup("<i class='fa fa-address-book'/> {contact_name} <br/>").format(
                        contact_name=contact.get('name', {}).get('formatted_name', ''))
                    for phone in contact.get('phones'):
                        body += Markup("{phone_type}: {phone_number}<br/>").format(
                            phone_type=phone.get('type'), phone_number=phone.get('phone'))
                kwargs['body'] = body
            elif message_type == 'reaction':
                msg_uid = messages['reaction'].get('message_id')
                whatsapp_message = self.env['whatsapp.message'].sudo().search([('msg_uid', '=', msg_uid)])
                if whatsapp_message:
                    partner_id = channel.whatsapp_partner_id
                    emoji = messages['reaction'].get('emoji')
                    whatsapp_message.mail_message_id._post_whatsapp_reaction(reaction_content=emoji, partner_id=partner_id)
                    continue
            else:
                _logger.warning("Unsupported whatsapp message type: %s", messages)
                continue
            channel.message_post(whatsapp_inbound_msg_uid=messages['id'], **kwargs)

    def _process_messages(self, value):

        _logger.info(f"1")
        if 'messages' not in value and value.get('whatsapp_business_api_data', {}).get('messages'):
            value = value['whatsapp_business_api_data']

        wa_api = WhatsAppApi(self)

        for messages in value.get('messages', []):
            _logger.info(f"Emessages: {str(messages)}")
            parent_msg_id = False
            parent_id = False
            channel = False
            sender_name = value.get('contacts', [{}])[0].get('profile', {}).get('name')
            sender_mobile = messages['from']
            message_type = messages['type']
            _logger.info(f"sender_mobiler: {str(sender_mobile)}")
            # if 'context' in messages and messages['context'].get('id'):
            #     parent_whatsapp_message = self.env['whatsapp.message'].sudo().search(
            #         [('msg_uid', '=', messages['context']['id'])])
            #     if parent_whatsapp_message:
            #         parent_msg_id = parent_whatsapp_message.id
            #         parent_id = parent_whatsapp_message.mail_message_id
            #     if parent_id:
            #         channel = self.env['discuss.channel'].sudo().search([('message_ids', 'in', parent_id.id)], limit=1)

            # Partner phone
            sender_mobile_plus = sender_mobile
            if not sender_mobile.startswith("+"):
                sender_mobile_plus = f"+{sender_mobile}"

            partner = self.env['res.partner'].sudo().search(
                ['|', ('mobile', '=', sender_mobile_plus), ('mobile', '=', sender_mobile)], limit=1)
            country_id = False
            try:
                parsed_number = phonenumbers.parse(sender_mobile_plus, None)
                country_code = geocoder.region_code_for_number(parsed_number)
                country_id = self.env['res.country'].search([('code', '=', country_code)], limit=1).id
            except phonenumbers.NumberParseException as e:
                _logger.info(f"Error parsing phone number: {str(e)}")
            _logger.info(f"partner: {str(partner)}")
            if not partner:
                partner = self.env['res.partner'].sudo().create(
                    {'name': sender_name, 'mobile': sender_mobile, 'country_id': country_id})
            # End Partner phone
            # if ticket still opened
            base_number = sender_mobile if sender_mobile.startswith('+') else f'+{sender_mobile}'
            wa_number = base_number.lstrip('+')
            wa_formatted = wa_phone_validation.wa_phone_format(
                self.env.company,
                number=base_number,
                force_format="WHATSAPP",
                raise_exception=False,
            ) or wa_number

            open_ticket_id = self.env['helpdesk.ticket'].sudo().search([
                '|',
                ('partner_mobile', '=', wa_formatted),
                ('partner_phone', '=', wa_formatted),
                ('stage_status', 'not in', ['is_cancelled', 'is_closed']),
                ('create_date', '>=', fields.Datetime.now() - relativedelta(days=1))
            ],order='create_date desc', limit=1)

            # if channel still not ended
            current_channel_id = False
            if open_ticket_id:
                current_channel_id = self.env['discuss.channel'].sudo().search(
                [('is_ticket', '=', True), ('is_end_chat', '=', False), ('ticket_id', '=', open_ticket_id.id)], limit=1)
            feedback_type = ''
            if messages.get('button'):
                if messages['button'].get('payload') in ['yes', 'no']:
                    # send survey feedback
                    feedback_type = messages['button']['payload']
                    current_channel_id = self.env['discuss.channel'].sudo().search(
                        [('is_ticket', '=', True), ('ticket_id', '=', open_ticket_id.id)], limit=1)

            if current_channel_id:
                channel = current_channel_id
            else:
                # check phone number
                whatsapp_number = sender_mobile
                base_number = whatsapp_number if whatsapp_number.startswith('+') else f'+{whatsapp_number}'
                wa_number = base_number.lstrip('+')
                wa_formatted = wa_phone_validation.wa_phone_format(
                    self.env.company,
                    number=base_number,
                    force_format="WHATSAPP",
                    raise_exception=False,
                ) or wa_number

                queue_partner_ids = False
                queue_users = False
                notify_user_ids = False
                queue_id = self.env['discuss.queue'].sudo().search([('type', '=', 'chat')], limit=1)
                if queue_id:
                    queue_users = queue_id.user_ids.filtered(lambda x: x.open_channels_count < queue_id.max_chats)
                    _logger.info(f"queue_id: {str(queue_id)}")
                    _logger.info(f"queue_users: {str(queue_users)}")
                    queue_partner_ids = queue_users.mapped('partner_id')

                if queue_users and len(queue_users) > 0:
                    notify_user_ids = queue_users.sorted(lambda x: x.open_channels_count)[0] if queue_users else None
                else:
                    notify_user_ids = False
                _logger.info(f"queue_users: {str(queue_users)}")
                _logger.info(f"notify_user_ids: {str(notify_user_ids)}")
                # get available_agent
                new_ticket_id = self.env['helpdesk.ticket'].sudo().create({
                    'name': f"WhatsApp Message from {sender_name}",
                    'partner_id': partner.id,
                    'description': messages['text']['body'],
                    'company_id': self.env.company.id,
                    'user_id': notify_user_ids.id if notify_user_ids else False,
                })

                channel_name = sender_name + ' - #' + str(new_ticket_id.id)
                channel = self.env['discuss.channel'].sudo().with_context(tools.clean_context(self.env.context)).create({
                    'name':channel_name,
                    'channel_type': 'whatsapp',
                    'whatsapp_number': wa_formatted,
                    'whatsapp_partner_id': partner.id,
                    'wa_account_id': self.id,
                    'ticket_id': new_ticket_id.id,
                    'is_ticket': True,
                    'is_hold': notify_user_ids == False,
                })
                partners_to_notify = channel_member = channel.whatsapp_partner_id
                if notify_user_ids:
                    partners_to_notify += notify_user_ids.partner_id
                    # channel_member += self.supervisor_ids.mapped('partner_id')
                    channel_member += notify_user_ids.partner_id


                channel.channel_member_ids = [Command.clear()] + [Command.create({'partner_id': partner.id}) for partner
                                                                  in channel_member]
                channel._broadcast(partners_to_notify.ids)

            client_id = False
            channel_partner_id = False
            if channel.ticket_id:
                client_id = channel.ticket_id.commercial_partner_id
                channel_partner_id = channel.ticket_id.user_id
            feedback = self.env["survey.feedback.message"].sudo().create({
                "channel_id": channel.id,
                "agent_id": channel_partner_id.id if channel_partner_id else False,
                "feedback": str(feedback_type.lower()),
                "channel_type": channel.channel_type,
                "client_id": client_id.id if client_id else False,
            })


            kwargs = {
                'message_type': 'whatsapp_message',
                'author_id': channel.whatsapp_partner_id.id,
                'parent_msg_id': parent_msg_id,
                'subtype_xmlid': 'mail.mt_comment',
                'parent_id': parent_id.id if parent_id else None
            }
            if message_type == 'text':
                kwargs['body'] = plaintext2html(messages['text']['body'])
            elif message_type == 'button':
                kwargs['body'] = messages['button']['text']
            elif message_type in ('document', 'image', 'audio', 'video', 'sticker'):
                filename = messages[message_type].get('filename')
                mime_type = messages[message_type].get('mime_type')
                caption = messages[message_type].get('caption')
                datas = wa_api._get_whatsapp_document(messages[message_type]['id'])
                if not filename:
                    extension = mimetypes.guess_extension(mime_type) or ''
                    filename = message_type + extension
                kwargs['attachments'] = [(filename, datas)]
                if caption:
                    kwargs['body'] = plaintext2html(caption)
            elif message_type == 'location':
                url = Markup("https://maps.google.com/maps?q={latitude},{longitude}").format(
                    latitude=messages['location']['latitude'], longitude=messages['location']['longitude'])
                body = Markup('<a target="_blank" href="{url}"> <i class="fa fa-map-marker"/> {location_string} </a>').format(
                    url=url, location_string=_("Location"))
                if messages['location'].get('name'):
                    body += Markup("<br/>{location_name}").format(location_name=messages['location']['name'])
                if messages['location'].get('address'):
                    body += Markup("<br/>{location_address}").format(location_name=messages['location']['address'])
                kwargs['body'] = body
            elif message_type == 'contacts':
                body = ""
                for contact in messages['contacts']:
                    body += Markup("<i class='fa fa-address-book'/> {contact_name} <br/>").format(
                        contact_name=contact.get('name', {}).get('formatted_name', ''))
                    for phone in contact.get('phones'):
                        body += Markup("{phone_type}: {phone_number}<br/>").format(
                            phone_type=phone.get('type'), phone_number=phone.get('phone'))
                kwargs['body'] = body
            elif message_type == 'reaction':
                msg_uid = messages['reaction'].get('message_id')
                whatsapp_message = self.env['whatsapp.message'].sudo().search([('msg_uid', '=', msg_uid)])
                if whatsapp_message:
                    partner_id = channel.whatsapp_partner_id
                    emoji = messages['reaction'].get('emoji')
                    whatsapp_message.mail_message_id._post_whatsapp_reaction(reaction_content=emoji, partner_id=partner_id)
                    continue
            else:
                _logger.warning("Unsupported whatsapp message type: %s", messages)
                continue
            channel.message_post(whatsapp_inbound_msg_uid=messages['id'], **kwargs)
