import { Button, Collapse, Colors, NonIdealState, Spinner } from "@blueprintjs/core";
import Link from "next/link";
import React, { ReactNode, useMemo, useState } from "react";
import { Col, Row } from "react-bootstrap";
import { ProjectDeviceDetails, ProjectDevicePositionKeys, ProjectInfo } from "../../project_model";
import { formatDevicePositionNumber } from "../project_details";
import { ProjectFftDiff, fetchProjectDiffDataHook } from "./project_diff_model";

import { capitalizeFirstLetter } from "@/app/utils/string_utils";
import styles from './project_diff.module.css';

// displays the diff tables between two projects
export const ProjectDiffPage: React.FC<{ projectIdA: string, projectIdB: string }> = ({ projectIdA, projectIdB }) => {
    const { isLoading, loadError, diff } = fetchProjectDiffDataHook(projectIdA, projectIdB)
    return <ProjectDiffTables isLoading={isLoading} loadError={loadError} diff={diff} />
}


export const ProjectDiffTables: React.FC<{ isLoading: boolean, loadError: string, diff?: ProjectFftDiff }> = ({ isLoading, loadError, diff }) => {
    if (isLoading) {
        return <NonIdealState icon={<Spinner />} title="Loading Diff" description="Loading project data..." className="mt-5" />
    }

    if (loadError) {
        return <NonIdealState icon="error" title="Error" description={loadError} className="mt-5" />
    }

    if (!diff) {
        return <NonIdealState icon="blank" title="No Diff to Display" description="There is no diff to display" className="mt-5" />
    }

    return (
        <>
            <ProjectDiffTable diff={diff} type="new" />
            <ProjectDiffTable diff={diff} type="missing" />
            <ProjectDiffTable diff={diff} type="updated" />
            <ProjectDiffTable diff={diff} type="identical" defaultOpen={false} />
        </>
    )
}


const DiffTableHeading: React.FC<{ title?: ReactNode }> = ({ title }) => {
    return (
        <thead>
            {title ? <tr><th colSpan={17}><h5>{title}</h5></th></tr> : null}
            <tr>
                <th colSpan={5}></th>

                <th colSpan={3} className="text-center">Nominal Location (meters in LCLS coordinates)</th>
                <th colSpan={3} className="text-center">Nominal Dimension (meters)</th>
                <th colSpan={3} className="text-center">Nominal Angle (radians)</th>
                <th></th>
                <th>Approval</th>
            </tr>
            <tr>
                <th>FC</th>
                <th>Fungible</th>
                <th>TC Part No.</th>
                <th>State</th>
                <th>Comments</th>

                <th className="text-center">Z</th>
                <th className="text-center">X</th>
                <th className="text-center">Y</th>

                <th className="text-center">Z</th>
                <th className="text-center">X</th>
                <th className="text-center">Y</th>

                <th className="text-center">Z</th>
                <th className="text-center">X</th>
                <th className="text-center">Y</th>
                <th>Must Ray Trace</th>
                <th>Communications</th>
            </tr>
        </thead>
    )
}

// just for displaying data
export const ProjectDiffTable: React.FC<{ diff: ProjectFftDiff, type: 'new' | 'updated' | 'missing' | 'identical', defaultOpen?: boolean }> = ({ diff, type, defaultOpen = true }) => {
    const [collapsed, setCollapsed] = useState(!defaultOpen);

    const createProjectLink = (project: ProjectInfo, type: 'a' | 'b') => {
        const color = type == 'a' ? Colors.RED2 : Colors.BLUE2;
        return <Link style={{ color: color }} href={`/projects/${project._id}/`}>{project.name}</Link>
    }

    const titleDescription: ReactNode = useMemo(() => {
        switch (type) {
            case "new": return <>{diff.new.length} New devices in {createProjectLink(diff.a, 'a')} compared to {createProjectLink(diff.b, 'b')}</>
            case "updated": return <>{diff.updated.length} Updated devices in {createProjectLink(diff.a, 'a')} compared to {createProjectLink(diff.b, 'b')}</>
            case "missing": return <>{diff.missing.length} Missing devices from {createProjectLink(diff.a, 'a')} (they are present in {createProjectLink(diff.b, 'b')})</>
            case "identical": return <>{diff.identical.length} Identical devices in {createProjectLink(diff.a, 'a')} and {createProjectLink(diff.b, 'b')}</>
        }
    }, [diff, type])

    const renderDiffRows = (data: { a: ProjectDeviceDetails, b: ProjectDeviceDetails }[]) => {
        const formatValueIfNumber = (val: any, field: keyof ProjectDeviceDetails) => {
            if (field == "id" || field == "fc" || field == "fg") {
                return val;
            }
            const isPositionField = ProjectDevicePositionKeys.indexOf(field) >= 0;
            if (isPositionField) {
                return formatDevicePositionNumber(val);
            }
            return val;
        }

        const formatField = (val: any, field: keyof ProjectDeviceDetails) => {
            if (val === undefined || val == "") {
                // TODO: decide whether to display empty or just a single empty space?
                return "<empty>";
            }

            if (typeof val == "string" && val.trim() == "") {
                // html by default collapses multiple spaces into 1; since we would like to preserve
                // the exact number of spaces, an extra span is needed.
                return <span style={{ whiteSpace: 'pre' }}>{val}</span>;
            }

            return formatValueIfNumber(val, field)
        }

        const renderField = (a: ProjectDeviceDetails, b: ProjectDeviceDetails, field: keyof ProjectDeviceDetails) => {
            let isChanged = a[field] != b[field];
            if (!isChanged) {
                // if the value is empty, we just render empty tag
                return <span style={{ color: Colors.GRAY1 }}>{formatValueIfNumber(a[field], field)}</span>
            }

            // there is a change in fields (display both one under the other)
            let aData = formatField(a[field], field);
            let bData = formatField(b[field], field);
            return (
                <>
                    <span style={{ backgroundColor: Colors.RED5 }}>{aData}</span>
                    <br />
                    <span style={{ backgroundColor: Colors.BLUE5 }}>{bData}</span>
                </>
            )
        }

        return data.map(devices => {
            return (<tr key={devices.a.id}>
                <td>{renderField(devices.a, devices.b, 'fc')}</td>
                <td>{renderField(devices.a, devices.b, 'fg')}</td>
                <td>{renderField(devices.a, devices.b, 'tc_part_no')}</td>
                <td>{renderField(devices.a, devices.b, 'state')}</td>
                <td>{renderField(devices.a, devices.b, 'comments')}</td>

                <td>{renderField(devices.a, devices.b, 'nom_loc_z')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_loc_x')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_loc_y')}</td>

                <td>{renderField(devices.a, devices.b, 'nom_dim_z')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_dim_x')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_dim_y')}</td>

                <td>{renderField(devices.a, devices.b, 'nom_ang_z')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_ang_x')}</td>
                <td>{renderField(devices.a, devices.b, 'nom_ang_y')}</td>

                <td>{renderField(devices.a, devices.b, 'ray_trace')}</td>
                <td></td>
            </tr>
            )
        })
    }

    const renderDataRows = (data: ProjectDeviceDetails[]) => {
        return data.map(d => {
            return (
                <tr key={d.id}>
                    <td>{d.fc}</td>
                    <td>{d.fg}</td>
                    <td>{d.tc_part_no}</td>
                    <td>{d.state}</td>
                    <td>{d.comments}</td>

                    <td>{formatDevicePositionNumber(d.nom_loc_z)}</td>
                    <td>{formatDevicePositionNumber(d.nom_loc_x)}</td>
                    <td>{formatDevicePositionNumber(d.nom_loc_y)}</td>

                    <td>{formatDevicePositionNumber(d.nom_dim_z)}</td>
                    <td>{formatDevicePositionNumber(d.nom_dim_x)}</td>
                    <td>{formatDevicePositionNumber(d.nom_dim_y)}</td>

                    <td>{formatDevicePositionNumber(d.nom_ang_z)}</td>
                    <td>{formatDevicePositionNumber(d.nom_ang_x)}</td>
                    <td>{formatDevicePositionNumber(d.nom_ang_y)}</td>

                    <td>{d.ray_trace}</td>
                    <td></td>
                </tr>
            )
        })
    }

    const renderTableBody = () => {
        switch (type) {
            case 'new': return renderDataRows(diff.new);
            case 'missing': return renderDataRows(diff.missing);
            case 'identical': return renderDataRows(diff.identical);
            case 'updated': return renderDiffRows(diff.updated);
        }
    }

    const noDevices: boolean = useMemo(() => {
        switch (type) {
            case 'new': return diff.new.length == 0;
            case 'missing': return diff.missing.length == 0;
            case 'identical': return diff.identical.length == 0;
            case 'updated': return diff.updated.length == 0;
        }
    }, [diff]);


    if (type == "missing" && diff.missing.length == 0) {
        // no need to display the missing table if nothing is missing
        return null;
    }

    return (
        <div className="mb-5">
            <Row className="align-items-center">
                <Col className="col-auto pe-0">
                    <Button icon={collapsed ? "chevron-right" : "chevron-down"} minimal={true}
                        onClick={(e) => setCollapsed((collapsed) => !collapsed)}
                    />
                </Col>
                <Col className="ps-0">
                    <h5 className="m-0">{titleDescription}</h5>
                </Col>
            </Row>

            <Collapse isOpen={!collapsed} keepChildrenMounted={true}>
                {noDevices ?
                    <NonIdealState icon="clean" title={`No ${capitalizeFirstLetter(type)} Devices`} description={`There are no ${type} devices`} />
                    :
                    <div className="table-responsive" style={{ maxHeight: "75vh" }}>
                        <table className={`table table-sm table-bordered table-striped table-sticky ${styles.diffTable}`}>
                            <DiffTableHeading />
                            <tbody>{renderTableBody()}</tbody>
                        </table>
                    </div>
                }
            </Collapse>
        </div>
    )
}