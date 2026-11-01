"use client";

import { useState } from "react";
import { CandidateCard } from "@/components/builder/CandidateCard";
import { DuplicateCheckForm } from "@/components/builder/DuplicateCheckForm";
import { ProposeForm } from "@/components/builder/ProposeForm";
import type { DuplicateCheckResult } from "@/lib/api/types";

/**
 * Runs the first step of the Builder: from a described need to reusing an agent or proposing one.
 *
 * Exists to reuse before creating. Proposing appears only when no agent resembles the need, or after
 * the person says the candidate is not what they wanted.
 *
 * @returns The page content.
 */
export function BuilderIntake() {
  const [description, setDescription] = useState("");
  const [check, setCheck] = useState<DuplicateCheckResult | null>(null);
  const [rejectedCandidate, setRejectedCandidate] = useState(false);

  function handleDescriptionChange(value: string): void {
    setDescription(value);
    setCheck(null);
    setRejectedCandidate(false);
  }

  const candidate = check?.candidate ?? null;
  const canPropose = check !== null && (candidate === null || rejectedCandidate);
  return (
    <>
      <h1 className="page-title">Builder</h1>
      <p className="page-intro">Describe lo que necesitas. Primero buscamos si ya existe un agente que lo resuelva.</p>
      <div className="max-w-2xl space-y-4">
        <DuplicateCheckForm description={description} onDescriptionChange={(value) => handleDescriptionChange(value)} onChecked={(result) => setCheck(result)} />
        {check && candidate && !rejectedCandidate && (
          <CandidateCard candidate={candidate} verdict={check.verdict} reason={check.reason} onReject={() => setRejectedCandidate(true)} />
        )}
        {check && !candidate && <p className="text-sm text-slate-600">No encontramos un agente que lo resuelva. {check.reason}</p>}
        {canPropose && <ProposeForm description={description} />}
      </div>
    </>
  );
}
