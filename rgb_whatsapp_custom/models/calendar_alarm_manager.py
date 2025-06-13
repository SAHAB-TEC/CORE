# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields


class AlarmManager(models.AbstractModel):
    _inherit = 'calendar.alarm_manager'

    @api.model
    def _send_reminder(self):
        """ Cron method, overridden here to send SMS reminders as well
        """
        super()._send_reminder()
        """ Send whatsapp reminders for calendar events """

        events_by_alarm = self._get_events_by_alarm_to_notify('email')
        if not events_by_alarm:
            return

        event_ids = list(set(event_id for event_ids in events_by_alarm.values() for event_id in event_ids))
        events = self.env['calendar.event'].browse(event_ids)

        for event in events:
            invited_min_attendees = self.env['calendar.attendee'].search([('event_id', '=', event.id), ('stop_reminder_desc', '=', False), ('is_invited_min', '=', True)])
            invited_attendees = self.env['calendar.attendee'].search([('event_id', '=', event.id), ('stop_reminder', '=', False), ('is_invited', '=', True)])

            for attendee in invited_min_attendees:
                attendee.send_whatsapp_reminder_description()

            for attendee in invited_attendees:
                attendee.send_whatsapp_reminder_one()