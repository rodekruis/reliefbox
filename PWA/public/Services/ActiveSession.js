export class ActiveSession {
    constructor(database) {
        console.info("ℹ️ Constructing active session, should only happen once ");
        this.database = database;
    }
    get nameOfLastViewedDistribution() {
        return this._nameOfLastViewedDistribution;
    }
    set nameOfLastViewedDistribution(value) {
        console.log("ℹ️ name of last viewed distribution is now:");
        console.log(value);
        this._nameOfLastViewedDistribution = value;
    }
    get nameOfLastUsedDistributionInputMethod() {
        return this._nameOfLastUsedDistributionInputMethod;
    }
    set nameOfLastUsedDistributionInputMethod(value) {
        console.log("ℹ️ name of last used distribution input method is now:");
        console.log(value);
        this._nameOfLastUsedDistributionInputMethod = value;
    }
}
export class ActiveSessionContainer {
    constructor(activeSession) {
        this.activeSession = activeSession;
    }
}
