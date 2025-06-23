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
                _logger.info("Received button message: %s", messages['button'].get('payload'))
                if (messages['button'].get('payload') in ['ايقاف','ايقاف ']
                        or "ايقاف" in messages['button'].get('payload')
                        or "stop" in messages['button'].get('payload').lower()):
                    # stop receiving messages
                    _logger.info("Stop : %s", messages['button'].get('payload'))
                    sender_partner = self.env['res.partner'].sudo().search(['|',('mobile', '=', sender_mobile),('phone', '=', sender_mobile)], limit=1)
                    attendee_id = channel.attendee_id
                    _logger.info("Attendee ID: %s", attendee_id)
                    _logger.info("Sender Partner: %s", sender_partner)
                    if attendee_id:
                        _logger.info("Attendee Type: %s", channel.attenee_type)
                        if channel.attenee_type == 'reminder':
                            attendee_id.sudo().write({
                                'stop_reminder': True,
                            })
                        if channel.attenee_type == 'reminder_desc':
                            attendee_id.sudo().write({
                                'stop_reminder_desc': True,
                            })

                # "تأكيد" or "confirm" in messages['button'].get('payload').lower():
                if (messages['button'].get('payload') in ['تأكيد', 'تأكيد ']
                        or "تأكيد" in messages['button'].get('payload')
                        or "confirm" in messages['button'].get('payload').lower()):
                    sender_partner = self.env['res.partner'].sudo().search(['|', ('mobile', '=', sender_mobile), ('phone', '=', sender_mobile)], limit=1)
                    attendee_id = channel.attendee_id
                    if attendee_id:
                        _logger.info("Attendee Type: %s", channel.attenee_type)
                        attendee_id.sudo().do_accept()
                    else:
                        _logger.info("there is no attendee_id for this channel: %s", channel.id)
                        # get attendee
                        attendee_id = self.env['calendar.attendee'].sudo().search([('partner_id', '=', sender_partner.id), ('event_id', '=', channel.event_id.id)], limit=1)



                if (messages['button'].get('payload') in ['الغاء', 'الغاء ']
                        or "الغاء" in messages['button'].get('payload')
                        or "cancel" in messages['button'].get('payload').lower()):
                    sender_partner = self.env['res.partner'].sudo().search(['|', ('mobile', '=', sender_mobile), ('phone', '=', sender_mobile)], limit=1)
                    attendee_id = channel.attendee_id
                    if attendee_id:
                        _logger.info("Attendee Type: %s", channel.attenee_type)
                        attendee_id.sudo().do_decline()
                    else:
                        _logger.info("there is no attendee_id for this channel: %s", channel.id)

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
