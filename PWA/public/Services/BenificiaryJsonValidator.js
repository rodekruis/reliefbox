export class BenificiaryJsonValidator {
    static isValidBenificiaryJson(json) {
        const rows = this.rowsFromJson(json);
        if (rows.length == 0) {
            console.log("Expected more than zero rows of data");
            return false;
        }
        //All table rows have same keys, therefore only checking first
        if (!this.rowHasCodeColumn(rows[0])) {
            console.log("Expected row to have column named code");
            return false;
        }
        return true;
    }
    static rowsFromJson(json) {
        return Object.values(json);
    }
    static rowHasCodeColumn(jsonRow) {
        return Object.keys(jsonRow)
            .indexOf("code") > -1;
    }
}
