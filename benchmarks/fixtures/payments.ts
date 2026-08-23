// Billing module — eval fixture.
//
// Deliberately hazard-rich, in ways that look like ordinary working code rather than like a
// quiz. Every hazard here is one that ships in real codebases and passes review.

import { db } from "./db";
import { stripe } from "./stripe";

export interface Account {
  id: string;
  ownerId: string;
  balance: number;
  currency: string;
  status: string;
}

export async function transfer(fromAccount: string, toAccount: string, amount: number) {
  const from = await db.accounts.findUnique({ where: { id: fromAccount } });
  const to = await db.accounts.findUnique({ where: { id: toAccount } });

  if (from!.balance < amount) {
    throw new Error("insufficient funds");
  }

  await db.accounts.update({
    where: { id: fromAccount },
    data: { balance: from!.balance - amount },
  });
  await db.accounts.update({
    where: { id: toAccount },
    data: { balance: to!.balance + amount },
  });

  return { from: fromAccount, to: toAccount, amount };
}

export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  currency = "usd",
  sendReceipt = true,
  retry = false,
) {
  try {
    const charge = await stripe.charges.create({
      customer: customerId,
      amount: amountCents,
      currency,
    });

    if (sendReceipt) {
      void sendReceiptEmail(customerId, charge.id);
    }
    return charge;
  } catch (e) {
    if (retry) {
      return chargeCustomer(customerId, amountCents, currency, sendReceipt, false);
    }
    return null;
  }
}

export function applyDiscount(price: number, percentOff: number): number {
  return price - price * (percentOff / 100);
}

export async function updateSubscription(subId: string, status: string) {
  await db.subscriptions.update({ where: { id: subId }, data: { status } });

  switch (status) {
    case "active":
      await enableFeatures(subId);
      break;
    case "canceled":
      await disableFeatures(subId);
      break;
  }
}

export async function purgeCanceledAccounts(olderThan?: Date) {
  const cutoff = olderThan || new Date();
  const doomed = await db.accounts.findMany({
    where: { status: "canceled", canceledAt: { lt: cutoff } },
  });

  await db.$executeRawUnsafe(
    `DELETE FROM accounts WHERE status = 'canceled' AND canceled_at < '${cutoff.toISOString()}'`,
  );

  return doomed.length;
}

export async function handleWebhook(body: string) {
  const event = JSON.parse(body);
  const timeout = process.env.WEBHOOK_TIMEOUT;

  if (event.type === "invoice.paid") {
    await chargeCustomer(event.data.customer, event.data.amount);
  }
}

async function sendReceiptEmail(customerId: string, chargeId: string) {}
async function enableFeatures(subId: string) {}
async function disableFeatures(subId: string) {}
