<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('pets', function (Blueprint $table) {
            $table->id();
            $table->timestamps();
            $table->string('name');
            $table->integer('breed_id');
            $table->date('date_of_birth')->nullable();
            $table->string('gender');
            $table->float('weight')->nullable();
            $table->integer('location_id');
            $table->text('description')->nullable();
            $table->string('image')->nullable();
            $table->boolean('is_puppy');
            $table->integer('litter_id')->nullable();
            $table->boolean('has_microchip');
            $table->boolean('has_vaccination');
            $table->boolean('has_healthcertificate');
            $table->boolean('has_dewormed');
            $table->boolean('has_birthcertificate');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('pets');
    }
};
