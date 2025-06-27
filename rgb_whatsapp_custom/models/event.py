from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import pytz, html2plaintext
import logging



_logger = logging.getLogger(__name__)

class RemindersHours(models.Model):
    _name = 'reminders.hours'
    _description = 'Reminders Hours'

    name = fields.Char(string='Reminder Time', required=True)


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    phone = fields.Char(string='Phone', compute='_compute_phone', store=True)
    invitation_title = fields.Char(string='Invitation Title', default='تمت دعوتك الي ', store=True)

    # reminders field selection with multi select contains from 01:00 AM to 12:00 PM
    reminder_hours_ids = fields.Many2many('reminders.hours')


    def send_whatsapp_invite(self):
        self.ensure_one()
        attendee = self.attendee_ids
        if not attendee:
            raise UserError("No attendees found for this event.")

        for attendee in attendee:
            attendee.send_whatsapp_invite()

    def send_whatsapp_invite_description(self):
        self.ensure_one()
        attendee = self.attendee_ids
        if not attendee:
            raise UserError("No attendees found for this event.")

        for attendee in attendee:
            attendee.send_whatsapp_invite_description()

    def send_whatsapp_reminder(self):
        for event in self:
            if event.phone:
                message = f"{event.invitation_title} {event.name} في {event.start}"
                whatsapp_template = self.env.ref('rgb_whatsapp_custom.rgb_new_whatsapp_template_calendar_reminder')
                if whatsapp_template:
                    whatsapp_template.message_post(event.phone, message)
                print(f"Sending WhatsApp message to {event.phone}: {message}")
            else:
                print("No phone number available for this event.")

    @api.depends('partner_ids')
    def _compute_phone(self):
        for event in self:
            phone = False
            if event.partner_ids:
                phone = event.partner_ids[0].phone
            event.phone = phone

    def _get_current_hour_label(self):
        """Return current hour in 12-hour format with AM/PM"""
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'Africa/Tripoli'
        user_tz = pytz.timezone(tz_name)

        # Get UTC now as a timezone-aware datetime
        utc_now = datetime.now(pytz.utc)

        # Convert UTC time to user local time
        local_now = utc_now.astimezone(user_tz)

        current_local_hour = local_now.replace(minute=0, second=0, microsecond=0).strftime('%-I:00 %p')
        _logger.warning("User timezone: %s", user_tz)
        _logger.warning("Current local hour label: %s", current_local_hour)

        return current_local_hour

    @api.model
    def cron_reminder_to_invitees(self):
        """Send reminder to event invitees matching the current hour"""
        hour_label = self._get_current_hour_label()
        _logger.warning("Current hour label for reminder: %s", hour_label)
        matching_events = self.search([('start', '>', datetime.now())])
        _logger.warning("Found %d events for reminder", len(matching_events))
        for event in matching_events:
            if hour_label in event.reminder_hours_ids.mapped('name'):
                for invitee in event.attendee_ids.filtered(lambda a: not a.stop_reminder and a.is_invited and a.state != 'declined'):
                    invitee.send_whatsapp_reminder_one()

    @api.model
    def cron_reminder_from_description(self):
        """Send reminder based on event description matching the current hour"""
        hour_label = self._get_current_hour_label()
        events = self.search([('start', '<', datetime.now())])
        for event in events:
            if hour_label in event.reminder_hours_ids.mapped('name'):
                for invitee in event.attendee_ids.filtered(lambda a: not a.stop_reminder_desc and a.is_invited_min and a.state != 'declined'):
                    invitee.send_whatsapp_reminder_description_one()

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    is_whatsapp_calender = fields.Boolean(string='Is WhatsApp Calendar', default=False,
                                          help="Indicates if this channel is used for WhatsApp calendar events.")
    attendee_id = fields.Many2one('calendar.attendee', string='Attendee',
                                  help="Reference to the calendar attendee associated with this channel.")
    attenee_type = fields.Selection([
        ('reminder', 'Reminder'),
        ('reminder_desc', 'Reminder Description'),
        ('invite_min', 'Invite Min'),
        ('invite', 'Invite')
    ], string='Attendee Type',
        help="Type of attendee for this channel, used to differentiate between reminders and invites.")


class Attendee(models.Model):
    _inherit = 'calendar.attendee'

    event_name = fields.Char(related='event_id.name', store=True)
    event_start_date = fields.Date(related='event_id.start_date', store=True)
    event_start_time = fields.Datetime(related='event_id.start', store=True)
    event_location = fields.Char(related='event_id.location', store=True)
    event_video_link = fields.Char(related='event_id.videocall_location', store=True)
    event_description = fields.Html(related='event_id.description', store=True)
    stop_reminder = fields.Boolean(string='Stop Reminder', default=False,
                                   help="If checked, this attendee will not receive reminders.")
    stop_reminder_desc = fields.Boolean(string='Stop Reminder Description', default=False,
                                        help="If checked, this attendee will not receive reminder descriptions.")
    is_invited = fields.Boolean(string='Is Invited', default=False,
                                help="Indicates if this attendee is invited to the event.")
    is_invited_min = fields.Boolean(string='Is Invited Min', default=False,
                                    help="Indicates if this attendee is invited with minimal information.")

    def send_whatsapp_invite(self):
        self.ensure_one()
        attendee = self
        template = self.env['whatsapp.template'].search(
            [('is_calender_event', '=', True), ('status', '=', 'approved')], limit=1
        )
        linke = " "
        if attendee.event_id.videocall_location and attendee.event_id.videocall_location.startswith('https://'):
            linke = "رابط الاجتماع : " + attendee.event_id.videocall_location
        if not template:
            return
        composer = self.env['whatsapp.composer'].create({
            'res_model': 'calendar.attendee',
            'res_ids': str(self.id),  # important: must be string, not list or int
            'wa_template_id': template.id,
            'batch_mode': False,
            'phone': self.partner_id.phone or self.partner_id.mobile or '',  # Optional if template uses dynamic phone
            'free_text_1': attendee.partner_id.name,
            'free_text_2': attendee.event_id.name,
            'free_text_3': attendee.event_id.start.date(),
            'free_text_4': attendee.event_id.start.astimezone(
                pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%I:%M %p'),
            'free_text_5': linke,
            'free_text_6': html2plaintext(attendee.event_id.description or ''),
            'free_text_7': attendee.event_id.invitation_title or '',
        })
        self.is_invited = True
        message = composer.sudo().action_send_whatsapp_template()
        wa_account = message.sudo().wa_account_id[:1]
        if wa_account:
            channel = wa_account.sudo()._find_active_channel(message.mobile_number_formatted)
            if channel:
                channel.write({
                    'name': f"WhatsApp Reminder: {attendee.event_id.name}",
                    'is_whatsapp_calender': True,
                    'attendee_id': attendee.id,
                    'attenee_type': 'invite',
                })
        else:
            _logger.warning("No WhatsApp Account found for message ID %s", message.id)
    def send_whatsapp_invite_description(self):
        self.ensure_one()
        if not self.event_id:
            raise UserError("No event associated with this attendee.")

        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'invite_description'), ('status', '=', 'approved')], limit=1
        )

        if not template:
            raise UserError("No WhatsApp template found for sending invite.")
        composer = self.env['whatsapp.composer'].create({
            'res_model': 'calendar.attendee',
            'res_ids': str(self.id),  # important: must be string, not list or int
            'wa_template_id': template.id,
            'batch_mode': False,
            'phone': self.partner_id.phone or self.partner_id.mobile or '',  # Optional if template uses dynamic phone
            'free_text_1': self.event_id.start.astimezone(pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime(
                '%Y-%m-%d'),
            'free_text_2': self.event_id.start.astimezone(pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime(
                '%I:%M %p'),
            'free_text_3': html2plaintext(self.event_id.description or ''),
        })

        message = composer.sudo().action_send_whatsapp_template()
        self.is_invited_min = True
        wa_account = message.sudo().wa_account_id[:1]
        if wa_account:
            channel = wa_account.sudo()._find_active_channel(message.mobile_number_formatted)
            if channel:
                channel.write({
                    'name': f"WhatsApp Reminder: {self.event_id.name}",
                    'is_whatsapp_calender': True,
                    'attendee_id': self.id,
                    'attenee_type': 'invite',
                })
        else:
            _logger.warning("No WhatsApp Account found for message ID %s", message.id)

    def send_whatsapp_reminder(self):
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'reminder'), ('status', '=', 'approved')], limit=1
        )  # or specify manually

        if not template:
            raise UserError("No WhatsApp template found for Sale Order.")

        all_attendees = self.env['calendar.attendee'].search(
            [('event_id.start', '>=', fields.Datetime.now()), ('stop_reminder', '=', False), ('is_invited', '=', True)])

        for attendee in all_attendees:
            linke = "."
            if attendee.event_id.videocall_location and attendee.event_id.videocall_location.startswith('https://'):
                linke = "رابط الاجتماع : " + attendee.event_id.videocall_location
            if not template:
                return
            composer = self.env['whatsapp.composer'].create({
                'res_model': 'calendar.attendee',
                'res_ids': str(self.id),  # important: must be string, not list or int
                'wa_template_id': template.id,
                'batch_mode': False,
                'phone': self.partner_id.phone or self.partner_id.mobile or '',
                # Optional if template uses dynamic phone
                'free_text_1': attendee.partner_id.name,
                'free_text_2': attendee.event_id.name,
                'free_text_3': attendee.event_id.start.date(),
                'free_text_4': attendee.event_id.start.astimezone(
                    pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%I:%M %p'),
                'free_text_5': linke,
                'free_text_6': html2plaintext(attendee.event_id.description or ''),
            })
            message = composer.sudo().action_send_whatsapp_template()
            wa_account = message.sudo().wa_account_id[:1]
            if wa_account:
                channel = wa_account.sudo()._find_active_channel(message.mobile_number_formatted)
                if channel:
                    channel.write({
                        'name': f"WhatsApp Reminder: {attendee.event_id.name}",
                        'is_whatsapp_calender': True,
                        'attendee_id': attendee.id,
                        'attenee_type': 'invite',
                    })
            else:
                _logger.warning("No WhatsApp Account found for message ID %s", message.id)

    def send_whatsapp_reminder_one(self):
        self.ensure_one()
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'reminder'), ('status', '=', 'approved')], limit=1
        )  # or specify manually

        if not template:
            raise UserError("No WhatsApp template found for Sale Order.")

        attendee = self

        linke = "."
        if attendee.event_id.videocall_location and attendee.event_id.videocall_location.startswith('https://'):
            linke = "رابط الاجتماع : " + attendee.event_id.videocall_location
        if not template:
            return
        composer = self.env['whatsapp.composer'].create({
            'res_model': 'calendar.attendee',
            'res_ids': str(self.id),  # important: must be string, not list or int
            'wa_template_id': template.id,
            'batch_mode': False,
            'phone': self.partner_id.phone or self.partner_id.mobile or '',
            # Optional if template uses dynamic phone
            'free_text_1': attendee.partner_id.name,
            'free_text_2': attendee.event_id.name,
            'free_text_3': attendee.event_id.start.date(),
            'free_text_4': attendee.event_id.start.astimezone(
                pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%I:%M %p'),
            'free_text_5': linke,
            'free_text_6': html2plaintext(attendee.event_id.description or ''),
        })
        message = composer.sudo().action_send_whatsapp_template()
        wa_account = message.sudo().wa_account_id[:1]
        if wa_account:
            channel = wa_account.sudo()._find_active_channel(message.mobile_number_formatted)
            if channel:
                channel.sudo().write({
                    'name': f"WhatsApp Reminder: {attendee.event_id.name}",
                    'is_whatsapp_calender': True,
                    'attendee_id': attendee.id,
                    'attenee_type': 'invite',
                })
        else:
            _logger.warning("No WhatsApp Account found for message ID %s", message.id)
    def send_whatsapp_reminder_description(self):
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'reminder_description'), ('status', '=', 'approved'),
             ('lang_code', '=', 'ar')], limit=1
        )  # or specify manually

        if not template:
            raise UserError("No WhatsApp template found for Sale Order.")

        all_attendees = self.env['calendar.attendee'].search(
            [('event_id.start', '>=', fields.Datetime.now()), ('stop_reminder_desc', '=', False),
             ('is_invited_min', '=', True)])

        for attendee in all_attendees:
            composer = self.env['whatsapp.composer'].create({
                'res_model': 'calendar.attendee',
                'res_ids': str(attendee.id),  # important: must be string, not list or int
                'wa_template_id': template.id,
                'batch_mode': False,
                'phone': attendee.partner_id.phone or attendee.partner_id.mobile or '',
                # Optional if template uses dynamic phone
                'free_text_1': self.event_id.start.astimezone(
                    pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%Y-%m-%d'),
                'free_text_2': self.event_id.start.astimezone(
                    pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%I:%M %p'),
                'free_text_3': html2plaintext(self.event_id.description or ''),
            })

            message = composer.sudo().action_send_whatsapp_template()
            wa_account = message.wa_account_id[:1]
            if wa_account:
                channel = wa_account._find_active_channel(message.mobile_number_formatted)
                if channel:
                    channel.write({
                        'name': f"WhatsApp Reminder: {attendee.event_id.name}",
                        'is_whatsapp_calender': True,
                        'attendee_id': attendee.id,
                        'attenee_type': 'invite',
                    })
            else:
                _logger.warning("No WhatsApp Account found for message ID %s", message.id)

    def send_whatsapp_reminder_description_one(self):
        self.ensure_one()
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'reminder_description'), ('status', '=', 'approved'),
             ('lang_code', '=', 'ar')], limit=1
        )  # or specify manually

        if not template:
            raise UserError("No WhatsApp template found for Sale Order.")

        attendee = self

        composer = self.env['whatsapp.composer'].create({
            'res_model': 'calendar.attendee',
            'res_ids': str(attendee.id),  # important: must be string, not list or int
            'wa_template_id': template.id,
            'batch_mode': False,
            'phone': attendee.partner_id.phone or attendee.partner_id.mobile or '',
            # Optional if template uses dynamic phone
            'free_text_1': self.event_id.start.astimezone(
                pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%Y-%m-%d'),
            'free_text_2': self.event_id.start.astimezone(
                pytz.timezone(self.env.context.get('tz') or 'UTC')).strftime('%I:%M %p'),
            'free_text_3': html2plaintext(self.event_id.description or ''),
        })

        message = composer.sudo().action_send_whatsapp_template()
        wa_account = message.wa_account_id[:1]
        if wa_account:
            channel = wa_account._find_active_channel(message.mobile_number_formatted)
            if channel:
                channel.write({
                    'name': f"WhatsApp Reminder: {attendee.event_id.name}",
                    'is_whatsapp_calender': True,
                    'attendee_id': attendee.id,
                    'attenee_type': 'invite',
                })
        else:
            _logger.warning("No WhatsApp Account found for message ID %s", message.id)
