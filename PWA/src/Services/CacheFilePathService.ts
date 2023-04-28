import { BeneficiaryDataUploadHandler } from "../FetchEventHandlers/BeneficiaryDataUploadHandler.js";
import { ChooseBenificiaryCodeInputMethodHandler } from "../FetchEventHandlers/ChooseBenificiaryCodeInputMethodHandler.js";
import { CreateDistributionRequestHandler } from "../FetchEventHandlers/CreateDistributionRequestHandler.js";
import { DeleteDistributionPostHandler } from "../FetchEventHandlers/DeleteDistributionPostHandler.js";
import { FetchEventHandlers } from "../FetchEventHandlers/FetchEventHandlers.js";
import { ListDistributionRequestHandler } from "../FetchEventHandlers/ListDistributionRequestHandler.js";
import { NameDistributionRequestHandler } from "../FetchEventHandlers/NameDistributionRequestHandler.js";
import { SelectDistributionRequestHandler } from "../FetchEventHandlers/SelectDistributionRequestHandler.js";
import { UploadDataHandler } from "../FetchEventHandlers/UploadDataHandler.js";
import { BenificiarySpreadSheetRow } from "../Models/BenificiarySpreadSheetRow.js";
import { DeleteDistributionPost } from "../Models/DeleteDistributionPost.js";
import { Distribution } from "../Models/Distribution.js";
import { SelectDistributionPost } from "../Models/SelectDistributionPost.js";
import { RouteEvents } from "../RouteEvents.js";
import { BenificiaryInfoService } from "./BenificiaryInfoService.js";
import { BenificiaryJsonValidator } from "./BenificiaryJsonValidator.js";
import { Database } from "./Database.js";
import { DeserialisationService } from "./DeserialisationService.js";
import { FormParser } from "./FormParser.js";


export class CacheFilePathService {
  pathsOfFilesToCache(): string[] {
    return [
        this.pagePaths(),
        this.modelPaths(),
        this.toplevelScriptsPaths(),
        this.fetchEventHanderPaths(),
        this.interfacesPaths(),
        this.externalLibrariesPaths(),
        this.servicePaths()
    ].reduce((previousArray, currentValue) => {
        return previousArray.concat(currentValue)
    }, [])
  }

  private pagePaths(): string[] {
    return [
        RouteEvents.template,
        RouteEvents.home, 
        RouteEvents.distributionsHome, 
        RouteEvents.nameDistribution, 
        RouteEvents.listDistributions,
        RouteEvents.deleteDistribution, 
        RouteEvents.uploadData, 
        RouteEvents.uploadDataError,
        RouteEvents.chooseBenificiaryCodeInputMethodPage
      ]
  } 

  private toplevelScriptsPaths(): string[] {
    return this.pathsForTypesInFolder("", [ 
      "app",
      "sw",
      "navbar-burger",
      RouteEvents.name
    ]);
  }

  private externalLibrariesPaths(): string[] {
    return this.pathsForTypesInFolder("ExternalLibraries", [
      "mustache",
      "xlsx.full.min"
    ]);
  } 

  private modelPaths(): string[] {
    return this.pathsForTypesInFolder("Models", [
      BenificiarySpreadSheetRow.name,
      Distribution.name,
      DeleteDistributionPost.name,
      SelectDistributionPost.name,
    ]);
  }

  private servicePaths(): string[] {
    return this.pathsForTypesInFolder("Services", [
        BenificiaryInfoService.name,
        BenificiaryJsonValidator.name,
        CacheFilePathService.name,
        Database.name,
        DeserialisationService.name,
        FormParser.name,
      ])
  }

  private fetchEventHanderPaths(): string[] {
    return this.pathsForTypesInFolder("FetchEventHandlers", [
        BeneficiaryDataUploadHandler.name,
        CreateDistributionRequestHandler.name,
        DeleteDistributionPostHandler.name,
        FetchEventHandlers.name,
        ListDistributionRequestHandler.name,
        NameDistributionRequestHandler.name,
        SelectDistributionRequestHandler.name,
        UploadDataHandler.name,
        ChooseBenificiaryCodeInputMethodHandler.name
    ])
  }

  private interfacesPaths(): string[] {
    return this.pathsForTypesInFolder("Interfaces", [
        "FetchEvent",
        "FetchEventHandler"
    ])
  }

  private pathsForTypesInFolder(folder: string, typeNames: String[], extension: string = ".js"): string[] {
    return typeNames.map((name) => this.pathForTypeInFolder(name, folder, extension));
  }

  private pathForTypeInFolder(typeName: String, folder: string, extension: string = ".js"): string {
    let path = "/"
    if(folder.length > 0) {
        path += folder + "/"
    }
    path += typeName + extension

    return path
  }
}
