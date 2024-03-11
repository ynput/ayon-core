// Copyright Epic Games, Inc. All Rights Reserved

#pragma once

#include "Editor.h"
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "DeadlineServiceTimerManager.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnTimerInterval);

/**
 * A Deadline Service timer class used for executing function calls on an interval. This class
 * can be used by other deadline implementations that use the deadline service to get notifications
 * when an update timer is executed by the service. 
 */
UCLASS(Blueprintable)
class DEADLINESERVICE_API UDeadlineServiceTimerManager : public UObject
{
	GENERATED_BODY()

public:
	/** Multicast Delegate to bind callable functions  */
	UPROPERTY(BlueprintAssignable, Category = "Deadline Service Timer Event")
	FOnTimerInterval OnTimerIntervalDelegate;
	
	/**
	 * Set a timer to execute a delegate. This timer is also used by the deadline service to periodically get updates
	 * on submitted jobs. This method returns a time handle reference for this function. This handle can be used at a
	 * later time to stop the timer.
	 *
	 * @param TimerInterval		Float timer intervals in seconds. Default is 1.0 seconds.
	 * @param bLoopTimer		Determine whether to loop the timer. By default this is true
	 */
	UFUNCTION(BlueprintCallable, Category = "Deadline Service Timer")
	FTimerHandle StartTimer(float TimerInterval=1.0, bool bLoopTimer=true )
	{
		
		GEditor->GetTimerManager()->SetTimer(
			DeadlineServiceTimerHandle,
			FTimerDelegate::CreateUObject(this, &UDeadlineServiceTimerManager::OnTimerEvent),
			TimerInterval,
			bLoopTimer
			);
		
		return DeadlineServiceTimerHandle;
		
	}

	/**
	 * Function to stop the service timer. 
	 *
	 * @param TimerHandle	Timer handle to stop
	 */
	UFUNCTION(BlueprintCallable, Category = "Deadline Service Timer")
	void StopTimer(FTimerHandle TimerHandle)
	{
		// Stop the timer
		GEditor->GetTimerManager()->ClearTimer(TimerHandle);
	}

private:
	/** Internal Timer handle */
	FTimerHandle DeadlineServiceTimerHandle;

protected:

	/**Internal function to broadcast timer delegate on the editor timer interval. */
	UFUNCTION()
	void OnTimerEvent() const
	{
		OnTimerIntervalDelegate.Broadcast();
	}
};
