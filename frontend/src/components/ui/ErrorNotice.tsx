/**
 * Shows a failure to the person.
 *
 * @param props.message - The explanation of what failed.
 * @returns The notice, announced by screen readers.
 */
export function ErrorNotice({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </p>
  );
}
