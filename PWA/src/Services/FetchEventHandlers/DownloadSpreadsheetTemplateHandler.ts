import { RouteEvents } from "../../RouteEvents.js";
import { FetchEvent } from "../../Interfaces/FetchEvent.js";
import { FetchEventHandler } from "../../Interfaces/FetchEventHandler.js";
import { SpreadSheetService } from "../SpreadSheetService.js";

export class DownloadSpreadsheetTemplateHandler implements FetchEventHandler {
  canHandleEvent(event: FetchEvent): boolean {
    return event.request.url.includes(RouteEvents.downloadSpreadsheetTemplate);
  }

  async handleEvent(event: FetchEvent): Promise<Response> {
    try {
      const templateJson = [
        { "code": 1, "first name": "Aric", "last name": "Norwood", "your column": "your value" },
        { "code": 2, "first name": "Lira", "last name": "Calloway", "your column": "your value" },
        { "code": 3, "first name": "Daven", "last name": "Morrell", "your column": "your value" },
      ]

      return new Response(await SpreadSheetService.fileFromJson(templateJson), {
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': 'attachment; filename="data_template.xlsx"'
        }
      });
    } catch(error) {
      return Promise.reject(error);
    }
  }
}