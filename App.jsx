import { useRef, useState } from "react";
import "./App.css";
import CameraCapture from "./CameraCapture";

const API_URL = "http://127.0.0.1:8000";

export default function App() {
  const fileInputRef = useRef(null);

  const [cameraOpen, setCameraOpen] = useState(false);
  const [selectedSide, setSelectedSide] = useState("front");
  const [images, setImages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  function openCameraOrGallery() {
    fileInputRef.current?.click();
  }

  async function handleImageSelection(event) {
    const files = Array.from(event.target.files || []);
    const accepted = [];

    for (const file of files) {
      const quality = await checkImageQuality(file);

      if (!quality.passed) {
        setMessage(`${file.name}: ${quality.reason}`);
        continue;
      }

      accepted.push({
        id: crypto.randomUUID(),
        file,
        side: selectedSide,
        previewUrl: URL.createObjectURL(file),
        status: "ready",
        serverData: null,
        humanDecision: null
      });
    }

    setImages((current) => [...current, ...accepted]);
    event.target.value = "";
  }

  async function addCapturedFile(file, metadata) {
    const quality = await checkImageQuality(file);

    if (!quality.passed) {
      setMessage(`${file.name}: ${quality.reason}`);
      return;
    }

    const item = {
      id: crypto.randomUUID(),
      file,
      side: selectedSide,
      previewUrl: URL.createObjectURL(file),
      status: "ready",
      serverData: null,
      metadata,
      humanDecision: null
    };

    setImages((current) => [...current, item]);
    setMessage("Camera image captured successfully.");
  }

  function removeImage(id) {
    setImages((current) => {
      const target = current.find((item) => item.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.id !== id);
    });
  }
function downloadComplianceReport(item) {
  if (!item.serverData?.compliance_report) return;

  const fields = item.serverData.fields;
  const report = item.serverData.compliance_report;
  const humanDecision = item.humanDecision || "pending";

  const safe = (value) => value || "Not found";

  const ruleRows = report.rule_results
    ?.map(
      (rule) => `
        <tr>
          <td>${rule.rule}</td>
          <td>${rule.requirement}</td>
          <td>${rule.status}</td>
          <td>${rule.result}</td>
        </tr>
      `
    )
    .join("");

  const problemRows = report.problems.length
    ? report.problems
        .map(
          (problem) => `
            <li>
              <strong>${problem.field.replaceAll("_", " ").toUpperCase()}:</strong>
              ${problem.problem}
              <br />
              <small>${problem.rule}</small>
            </li>
          `
        )
        .join("")
    : "<li>No problems detected by automated checks.</li>";

  const reportWindow = window.open("", "_blank");

  reportWindow.document.write(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>Saayujya Compliance Report</title>

        <style>
          body {
            font-family: Arial, sans-serif;
            padding: 32px;
            color: #111827;
            line-height: 1.5;
          }

          h1 {
            margin-bottom: 4px;
            color: #1e3a8a;
          }

          h2 {
            margin-top: 28px;
            color: #1e3a8a;
            border-bottom: 2px solid #bfdbfe;
            padding-bottom: 6px;
          }

          .subtitle {
            color: #4b5563;
            margin-bottom: 24px;
          }

          .summary {
            padding: 16px;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            margin-bottom: 20px;
          }

          .status {
            font-weight: bold;
            font-size: 18px;
          }

          .partially_compliant {
            color: #92400e;
          }

          .compliant {
            color: #166534;
          }

          .non_compliant {
            color: #991b1b;
          }

          table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            page-break-inside: auto;
          }

          th,
          td {
            border: 1px solid #d1d5db;
            padding: 8px;
            text-align: left;
            vertical-align: top;
            font-size: 12px;
          }

          th {
            background: #dbeafe;
            color: #1e3a8a;
          }

          ul {
            padding-left: 20px;
          }

          li {
            margin-bottom: 10px;
          }

          .problems {
            padding: 14px;
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 8px;
            color: #991b1b;
          }

          .human {
            margin-top: 24px;
            padding: 14px;
            background: #fef3c7;
            border: 1px solid #fde68a;
            border-radius: 8px;
            color: #92400e;
            font-weight: bold;
          }

          .disclaimer {
            margin-top: 24px;
            font-size: 11px;
            color: #6b7280;
          }

          button {
            margin-top: 24px;
            padding: 10px 14px;
            border: none;
            border-radius: 6px;
            background: #1d4ed8;
            color: white;
            font-weight: bold;
            cursor: pointer;
          }

          @media print {
            button {
              display: none;
            }

            body {
              padding: 20px;
            }
          }
        </style>
      </head>

      <body>
        <h1>Saayujya Compliance Report</h1>
        <p class="subtitle">
          Automated Compliance Checker for Legal Metrology Packaged Commodity Declarations
        </p>

        <div class="summary">
          <p><strong>File Name:</strong> ${item.file.name}</p>
          <p><strong>Package Side:</strong> ${item.side}</p>
          <p class="status ${report.status}">
            Status: ${report.status.replaceAll("_", " ").toUpperCase()}
          </p>
          <p><strong>Score:</strong> ${report.score}/100</p>
          <p><strong>Checks Passed:</strong> ${report.passed_checks}/${report.total_checks}</p>
        </div>

        <h2>Extracted Fields</h2>
        <table>
          <tr><th>Field</th><th>Extracted Value</th></tr>
          <tr><td>Product Name</td><td>${safe(fields.product_name)}</td></tr>
          <tr><td>Manufacturer</td><td>${safe(fields.manufacturer)}</td></tr>
          <tr><td>Marketed By</td><td>${safe(fields.marketed_by)}</td></tr>
          <tr><td>Manufacturer Address</td><td>${safe(fields.manufacturer_address)}</td></tr>
          <tr><td>Net Quantity</td><td>${safe(fields.net_quantity)}</td></tr>
          <tr><td>MRP</td><td>${safe(fields.mrp)}</td></tr>
          <tr><td>Mfg Date</td><td>${safe(fields.mfg_date)}</td></tr>
          <tr><td>Use By / Best Before</td><td>${safe(fields.use_by_or_best_before)}</td></tr>
          <tr><td>Manufacturer FSSAI</td><td>${safe(fields.manufacturer_fssai)}</td></tr>
          <tr><td>Marketed By FSSAI</td><td>${safe(fields.marketed_by_fssai)}</td></tr>
          <tr><td>Email</td><td>${safe(fields.email)}</td></tr>
          <tr><td>Customer Care</td><td>${safe(fields.customer_care)}</td></tr>
          <tr><td>Storage Instruction</td><td>${safe(fields.storage_instruction)}</td></tr>
        </table>

        <h2>Problems Found</h2>
        <div class="problems">
          <ul>
            ${problemRows}
          </ul>
        </div>

        <h2>Rule Check Results</h2>
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Requirement</th>
              <th>Status</th>
              <th>Result</th>
            </tr>
          </thead>

          <tbody>
            ${ruleRows}
          </tbody>
        </table>

        <div class="human">
          Human Verification: ${humanDecision.replaceAll("_", " ").toUpperCase()}
          <br />
          Final human verification is required before enforcement, submission, or legal decision-making.
        </div>

        <p class="disclaimer">
          This report is generated for hackathon/demo purposes. It is based on OCR output and automated rule checks.
          OCR may misread small, blurred, reflective, curved, or low-contrast text. Final compliance must be verified manually.
        </p>

        <button onclick="window.print()">Save as PDF</button>
      </body>
    </html>
  `);

  reportWindow.document.close();
}
function updateHumanVerification(id, decision) {
  setImages((current) =>
    current.map((item) =>
      item.id === id
        ? {
            ...item,
            humanDecision: decision
          }
        : item
    )
  );
}
async function uploadCombinedScan() {
  if (images.length < 2) {
    setMessage("Upload at least two images: one front and one back.");
    return;
  }

  const hasFront = images.some((item) => item.side === "front");
  const hasBack = images.some((item) => item.side === "back");

  if (!hasFront || !hasBack) {
    setMessage("Please upload both a front image and a back image.");
    return;
  }

  setUploading(true);
  setMessage("");

  try {
    const formData = new FormData();

    images.forEach((item) => {
      formData.append("images", item.file);
      formData.append("sides", item.side);
    });

    formData.append("capture_method", "combined_front_back");
    formData.append("client_timestamp", new Date().toISOString());

    const response = await fetch(`${API_URL}/api/v1/combined-scan`, {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Combined scan failed.");
    }

    setImages((current) =>
      current.map((item) => ({
        ...item,
        status: "included_in_combined_report"
      }))
    );

    setMessage("Combined front + back compliance report generated.");

    setImages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        file: {
          name: "Combined Front + Back Report"
        },
        side: "combined",
        previewUrl: images[0].previewUrl,
        status: "uploaded",
        serverData: data,
        humanDecision: null
      }
    ]);
  } catch (error) {
    setMessage(`Combined scan error: ${error.message}`);
  } finally {
    setUploading(false);
  }
}
  async function uploadAllImages() {
    if (images.length === 0) {
      setMessage("Capture or upload at least one label image first.");
      return;
    }

    setUploading(true);
    setMessage("");

    try {
      const updated = [];

      for (const item of images) {
        const formData = new FormData();

        formData.append("side", item.side);
        formData.append(
          "capture_method",
          item.metadata?.capture_method || "live_camera"
        );
        formData.append(
          "client_timestamp",
          item.metadata?.client_timestamp || new Date().toISOString()
        );
        formData.append("image", item.file);

        const response = await fetch(`${API_URL}/api/v1/scans`, {
          method: "POST",
          body: formData
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || "Upload failed.");
        }

        updated.push({
          ...item,
          status: "uploaded",
          serverData: data
        });
      }

      setImages(updated);
      setMessage("Images uploaded successfully. Compliance report generated.");
    } catch (error) {
      setMessage(`Upload error: ${error.message}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <header className="app-header">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">S</div>
            <div>
              <h1>Saayujya</h1>
              <p className="brand-kicker">Intelligent label compliance</p>
            </div>
          </div>
          <span className="status-pill"><i /> Scanner ready</span>
        </header>

        <section className="hero">
          <span className="eyebrow">LMPC CAMERA SCANNER</span>
          <h2>Compliance, captured clearly.</h2>
          <p className="subtitle">
            Scan packaged commodity labels and turn them into a clear, structured compliance review in seconds.
          </p>
        </section>

        <section className="scan-panel">
          <div className="section-heading">
            <div>
              <span className="step-label">01 · CAPTURE</span>
              <h3>Add a package label</h3>
            </div>
            <span className="secure-note">Private by design</span>
          </div>

        <label className="field-label" htmlFor="side">
          Package side
        </label>

        <select
          id="side"
          value={selectedSide}
          onChange={(event) => setSelectedSide(event.target.value)}
        >
          <option value="front">Front</option>
          <option value="back">Back</option>
          <option value="left_side">Left side</option>
          <option value="right_side">Right side</option>
          <option value="top">Top</option>
          <option value="bottom">Bottom</option>
        </select>

        <input
          ref={fileInputRef}
          className="hidden-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          multiple
          onChange={handleImageSelection}
        />

        <div className="button-row">
          <button className="primary-button" onClick={() => setCameraOpen(true)}>
            Open camera
          </button>

          <button className="secondary-button" onClick={openCameraOrGallery}>
            Choose photos
          </button>
        </div>

        <p className="hint">
          For best results, keep the label flat, evenly lit, and fully visible. Use the rear camera on mobile devices.
        </p>
        </section>

        {images.length > 0 && (
          <>
            <div className="section-heading results-heading"><div><span className="step-label">02 · REVIEW</span><h3>Captured labels</h3></div><span className="count-pill">{images.length} item{images.length === 1 ? "" : "s"}</span></div>

            <div className="image-grid">
              {images.map((item) => (
                <article className="image-card" key={item.id}>
                  <img src={item.previewUrl} alt={`${item.side} package`} />

                  <div className="image-meta">
                    <span>{item.side.replace("_", " ")}</span>
                    <small>{item.file.name}</small>

                    {item.serverData?.fields && (
                      <div className="extracted-fields">
                        <small><strong>Product Name:</strong> {item.serverData.fields.product_name || "Not found"}</small>
                        <small><strong>Manufacturer:</strong> {item.serverData.fields.manufacturer || "Not found"}</small>
                        <small><strong>Marketed By:</strong> {item.serverData.fields.marketed_by || "Not found"}</small>
                        <small><strong>Manufacturer Address:</strong> {item.serverData.fields.manufacturer_address || "Not found"}</small>
                        <small><strong>Net Quantity:</strong> {item.serverData.fields.net_quantity || "Not found"}</small>
                        <small><strong>MRP:</strong> {item.serverData.fields.mrp || "Not found"}</small>
                        <small><strong>Mfg Date:</strong> {item.serverData.fields.mfg_date || "Not found"}</small>
                        <small><strong>Use By / Best Before:</strong> {item.serverData.fields.use_by_or_best_before || "Not found"}</small>
                        <small><strong>Manufacturer FSSAI:</strong> {item.serverData.fields.manufacturer_fssai || "Not found"}</small>
                        <small><strong>Marketed By FSSAI:</strong> {item.serverData.fields.marketed_by_fssai || "Not found"}</small>
                        <small>
  <strong>All FSSAI Numbers:</strong>{" "}
  {item.serverData.fields.all_fssai_numbers?.length
    ? item.serverData.fields.all_fssai_numbers.join(", ")
    : "Not found"}
</small>
                        <small><strong>Email:</strong> {item.serverData.fields.email || "Not found"}</small>
                        <small><strong>Customer Care:</strong> {item.serverData.fields.customer_care || "Not found"}</small>
                        <small><strong>Storage:</strong> {item.serverData.fields.storage_instruction || "Not found"}</small>
                      </div>
                    )}

                    {item.serverData?.compliance_report && (
                      <div className="compliance-report">
                        <h3>Compliance Report</h3>

                        <p>
                          <strong>Status:</strong>{" "}
                          {item.serverData.compliance_report.status
                            .replace("_", " ")
                            .toUpperCase()}
                        </p>

                        <p>
                          <strong>Score:</strong>{" "}
                          {item.serverData.compliance_report.score}/100
                        </p>

                        <p>
                          <strong>Checks:</strong>{" "}
                          {item.serverData.compliance_report.passed_checks}/
                          {item.serverData.compliance_report.total_checks} passed
                        </p>

                        {item.serverData.compliance_report.problems.length > 0 && (
                          <div className="problems-box">
                            <strong>Problems Found:</strong>

                            {item.serverData.compliance_report.problems.map((problem, index) => (
                              <p key={index}>
                                {problem.problem} ({problem.rule})
                              </p>
                            ))}
                          </div>
                        )}

                        <div className="rules-table-wrap">
                          <table className="rules-table">
                            <thead>
                              <tr>
                                <th>Rule</th>
                                <th>Requirement</th>
                                <th>Status</th>
                                <th>Result</th>
                              </tr>
                            </thead>

                            <tbody>
                              {item.serverData.compliance_report.rule_results?.map((rule, index) => (
                                <tr key={index}>
                                  <td>{rule.rule}</td>
                                  <td>{rule.requirement}</td>
                                  <td>{rule.status}</td>
                                  <td>{rule.result}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        <p className="human-review">
  <strong>Human Verification:</strong>{" "}
  {(item.humanDecision || item.serverData.compliance_report.human_verification.status)
    .replace("_", " ")
    .toUpperCase()}
</p>

                        <div className="verification-actions">
                          <button onClick={() => updateHumanVerification(item.id, "verified_pass")}>
                            Verified Pass
                          </button>

                          <button onClick={() => updateHumanVerification(item.id, "verified_fail")}>
                            Verified Fail
                          </button>

                          <button
    type="button"
    onClick={() => updateHumanVerification(item.id, "needs_recheck")}
  >
    Needs Recheck
  </button>
</div>
                        {item.humanDecision && (
  <p className="human-decision">
    Final Human Decision: {item.humanDecision.replace("_", " ").toUpperCase()}
  </p>
)}

<button
  className="download-report-button"
  onClick={() => downloadComplianceReport(item)}
>
  Download Compliance Report
</button>

                       {item.humanDecision && (
  <p className="human-decision">
    Final Human Decision: {item.humanDecision.replace("_", " ").toUpperCase()}
  </p>
)}
                      </div>
                    )}

                    {item.serverData?.extracted_text && (
                      <details className="raw-ocr">
                        <summary>Show raw OCR text</summary>
                        <small>{item.serverData.extracted_text}</small>
                      </details>
                    )}

                    <small>Status: {item.status}</small>
                  </div>

                  <button
                    className="remove-button"
                    onClick={() => removeImage(item.id)}
                    disabled={uploading}
                  >
                    Remove
                  </button>
                </article>
              ))}
            </div>

            <button
              className="primary-button"
              onClick={uploadAllImages}
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Analyze labels"}
            </button><button
  className="secondary-button"
  onClick={uploadCombinedScan}
  disabled={uploading}
>
  Create combined report
</button> 
          </>
        )}

        {message && <p className="message">{message}</p>}

        {cameraOpen && (
          <CameraCapture
            onCaptured={addCapturedFile}
            onClose={() => setCameraOpen(false)}
            packageSide={selectedSide}
            scanSessionId="session_123"
          />
        )}
      </section>
    </main>
  );
}

async function checkImageQuality(file) {
  const imageUrl = URL.createObjectURL(file);

  try {
    const image = await new Promise((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = reject;
      element.src = imageUrl;
    });

    const minimumWidth = 1280;
    const minimumHeight = 720;

    if (image.width < minimumWidth || image.height < minimumHeight) {
      return {
        passed: false,
        reason: `Image resolution is too low. App detected ${image.width} x ${image.height}. Minimum needed is ${minimumWidth} x ${minimumHeight}.`
      };
    }

    return {
      passed: true,
      reason: "Basic quality check passed."
    };
  } finally {
    URL.revokeObjectURL(imageUrl);
  }
}